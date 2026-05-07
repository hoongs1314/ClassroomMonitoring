import json
import os
import re
import threading
import time
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from ultralytics import YOLO

from config import (
    CONF,
    DESC_JSON_FILE,
    EVENT_JSON_FILE,
    FRAME_FOCUS_DIR,
    FRAME_JSON_FILE,
    FRAME_SEC,
    IMG_SIZE,
    IOU,
    MODEL_PATH,
    POSE_RULE,
    QWEN_BASE_URL,
    QWEN_MODEL,
    ROOT_DIR,
    VIDEO_FILE,
    VIDEO_REL_PATH,
    make_output_dirs,
)
from pose_utils import PoseDebugUtils
from video_pose import (
    analyze_frame,
    build_events,
    ensure_output_dirs_clean,
    save_event_assets,
)

make_output_dirs()


class StartResponse(BaseModel):
    status: str
    message: str


STATUS_TEXT = {
    "NORMAL": "正常",
    "WEAK": "轻度异常",
    "STRONG": "明显异常",
    "INVALID": "无效",
}

REMIND_TEXT = {
    "FOCUS": "重点提醒",
    "NORMAL": "普通提醒",
}

ACTIVE_MIN_FRAMES = 3
END_GAP_SECONDS = FRAME_SEC * 1.1


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_media_url(path_str: str) -> str:
    file_path = path_str.replace("\\", "/").lstrip("/")
    return f"/media/{file_path}"


def status_text(status: str) -> str:
    return STATUS_TEXT.get(status, status)


def remind_text(level: str) -> str:
    return REMIND_TEXT.get(level, level)


def make_event_text(event: dict) -> str:
    return (
        f"疑似课堂异常，提醒级别：{event.get('reminder_text', remind_text('NORMAL'))}，"
        f"异常开始时间：{event.get('alert_start_time', event['start_time'])}，"
        f"已持续约 {event['duration_seconds']} 秒。"
    )


def get_area_text(box: list[float], frame_w: int, frame_h: int) -> str:
    mid_x = (box[0] + box[2]) / 2.0
    mid_y = (box[1] + box[3]) / 2.0

    if mid_x < frame_w * 0.33:
        x_text = "左侧"
    elif mid_x > frame_w * 0.66:
        x_text = "右侧"
    else:
        x_text = "中间"

    if mid_y < frame_h * 0.33:
        y_text = "前排"
    elif mid_y > frame_h * 0.66:
        y_text = "后排"
    else:
        y_text = "中排"

    return f"{x_text}{y_text}"


def pick_start_frame(event: dict) -> dict:
    frames = event.get("frames", [])
    if not frames:
        return {
            "time": event["start_time"],
            "timestamp_seconds": event["start_timestamp_seconds"],
        }

    if event.get("level") == "STRONG":
        for frame in frames:
            if frame["person"]["status"] == "STRONG":
                return frame

    top_ratio = event.get("peak_ratio")
    ratio_limit = 0.08
    if top_ratio is not None:
        ratio_limit = min(0.08, float(top_ratio) + 0.02)

    for frame in frames:
        person = frame["person"]
        ratio = person.get("ratio")
        if person["status"] not in {"WEAK", "STRONG"}:
            continue
        if ratio is None or ratio <= ratio_limit:
            return frame

    return frames[0]


def get_remind_level(event: dict) -> str:
    keep_strong = 0
    max_keep_strong = 0

    for frame in event.get("frames", []):
        if frame["person"]["status"] == "STRONG":
            keep_strong += 1
            max_keep_strong = max(max_keep_strong, keep_strong)
        else:
            keep_strong = 0

    return "FOCUS" if max_keep_strong >= 3 else "NORMAL"


def get_stage(event: dict, now_time: float, done: bool) -> str:
    if event.get("frame_count", 0) < ACTIVE_MIN_FRAMES:
        return "candidate"

    if done:
        return "closed"

    if now_time - event["end_timestamp_seconds"] >= END_GAP_SECONDS:
        return "closed"

    return "active"


def fill_event_data(event: dict, now_time: float = 0.0, done: bool = False):
    start_frame = pick_start_frame(event)
    event["alert_start_time"] = start_frame["time"]
    event["alert_start_timestamp_seconds"] = start_frame["timestamp_seconds"]
    event["display_time"] = event["alert_start_time"]
    event["reminder_level"] = get_remind_level(event)
    event["reminder_text"] = remind_text(event["reminder_level"])
    event["stage"] = get_stage(event, now_time, done)
    event["summary"] = make_event_text(event)


def image_to_data_url(image_path: str) -> str:
    import base64

    suffix = Path(image_path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    image_bytes = Path(image_path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"


def get_ai_key(event_id: int) -> str:
    return f"event_{event_id}"


def expand_focus_box(box: list[float], image_w: int, image_h: int, scale: float = 0.8) -> list[int]:
    x1, y1, x2, y2 = box
    box_w = x2 - x1
    box_h = y2 - y1
    pad_x = box_w * scale * 0.5
    pad_y = box_h * scale * 0.5
    out_x1 = max(0, int(round(x1 - pad_x)))
    out_y1 = max(0, int(round(y1 - pad_y)))
    out_x2 = min(image_w, int(round(x2 + pad_x)))
    out_y2 = min(image_h, int(round(y2 + pad_y)))
    return [out_x1, out_y1, out_x2, out_y2]


def make_frame_focus(event_id: int, frame: dict) -> str:
    FRAME_FOCUS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = FRAME_FOCUS_DIR / (
        f"event_{event_id:03d}_frame_{frame['frame_index']:06d}_person_{frame['person']['id']:02d}.jpg"
    )
    if out_file.exists():
        return str(out_file).replace("\\", "/")

    raw_file = ROOT_DIR / frame["raw_frame"]
    raw_img = cv2.imread(str(raw_file))
    if raw_img is None:
        return ""

    image_h, image_w = raw_img.shape[:2]
    box = frame["person"]["bbox"]
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    cut_x1, cut_y1, cut_x2, cut_y2 = expand_focus_box(box, image_w, image_h)
    if cut_x2 <= cut_x1 or cut_y2 <= cut_y1:
        return ""

    cut_img = raw_img[cut_y1:cut_y2, cut_x1:cut_x2].copy()
    color = (0, 255, 255) if frame["person"]["status"] == "WEAK" else (0, 0, 255)
    cv2.rectangle(
        cut_img,
        (x1 - cut_x1, y1 - cut_y1),
        (x2 - cut_x1, y2 - cut_y1),
        color,
        2,
    )
    cv2.imwrite(str(out_file), cut_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return str(out_file).replace("\\", "/")


def parse_json_text(text: str) -> dict | None:
    if not text:
        return None

    text = text.strip()
    text_list = [text]

    json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if json_block:
        text_list.insert(0, json_block.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text_list.append(text[start : end + 1])

    for item in text_list:
        try:
            data = json.loads(item)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def clean_ai_data(data, area_text: str, action_text: str) -> dict:
    if isinstance(data, str):
        parsed = parse_json_text(data)
        data = parsed if parsed is not None else {}

    sit = str(data.get("sit", "") or "").strip() if isinstance(data, dict) else ""
    action = str(data.get("action", "") or "").strip() if isinstance(data, dict) else ""
    text = str(data.get("text", "") or "").strip() if isinstance(data, dict) else ""

    if not sit:
        sit = area_text
    if not action:
        action = action_text
    if not text:
        text = f"{sit}，{action}"

    return {
        "sit": sit,
        "action": action,
        "text": text,
    }


def make_ai_prompt(event: dict, crop: dict) -> HumanMessage:
    prompt = (
        "你在看教室监控中的异常学生分析图。"
        "你会同时看到一张整帧教室画面和一张学生局部截图。"
        "请先根据整帧判断教室前方，也就是讲台、黑板或老师面向的方向。"
        "再以讲台为前方，判断学生大致位置。"
        "你必须只返回一个 JSON 对象，不要返回 markdown，不要返回代码块，不要返回额外解释。"
        'JSON 必须包含三个字段：sit、action、text。'
        'sit 表示学生位置，只需要识别大概位置，例如“中间前排”“讲台右侧中间”“讲台左侧后排”。'
        'action 表示学生行为，例如“睡觉”“趴桌”“低头”“低头学习”“玩手机”。'
        'text 是完整中文描述，格式尽量接近“讲台左侧后排，疑似趴桌睡觉。该学生长时间低头伏在桌面上，疑似处于睡觉状态。”'
        "不要写学生编号，不要遗漏任何字段。"
        f" 当前事件提醒级别：{event['reminder_text']}。"
        f" 当前检测状态：{crop['status_text']}。"
        f" 规则侧估计位置：{crop['position_text']}。"
        f" 当前比例值：{crop['ratio']}。"
    )

    content = [{"type": "text", "text": prompt}]
    if event.get("event_raw_image"):
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_to_data_url(event["event_raw_image"])},
            }
        )
    content.append(
        {
            "type": "image_url",
            "image_url": {"url": image_to_data_url(crop["image_path"])},
        }
    )
    return HumanMessage(content=content)


def get_llm() -> ChatOpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY，无法生成异常描述。")

    return ChatOpenAI(
        model=QWEN_MODEL,
        api_key=api_key,
        base_url=QWEN_BASE_URL,
        temperature=0.1,
    )


class MonitorEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.pose_utils = PoseDebugUtils(POSE_RULE)
        self.model = None
        self.cap = None
        self.worker = None
        self.running = False
        self.completed = False
        self.started_at = 0.0
        self.current_timestamp = 0.0
        self.duration_seconds = 0.0
        self.fps = 0.0
        self.total_frames = 0
        self.video_width = 0
        self.video_height = 0
        self.frame_records = []
        self.events = []
        self.event_map = {}
        self.ai_data = {"items": {}}
        self.wait_keys = set()
        self.event_ai = {}

    def _load_model(self):
        if self.model is None:
            self.model = YOLO(str(MODEL_PATH))

    def _open_video(self):
        cap = cv2.VideoCapture(str(VIDEO_FILE))
        if not cap.isOpened():
            raise RuntimeError(f"视频打开失败：{VIDEO_FILE}")
        return cap

    def _read_frame_at_second(self, second: float):
        if self.cap is None:
            return False, None
        if self.fps <= 0:
            self.cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
        else:
            target_frame = int(round(second * self.fps))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        return self.cap.read()

    def _reset_state(self):
        self.completed = False
        self.current_timestamp = 0.0
        self.frame_records = []
        self.events = []
        self.event_map = {}
        self.ai_data = {"items": {}}
        self.wait_keys = set()
        self.event_ai = {}
        if DESC_JSON_FILE.exists():
            DESC_JSON_FILE.unlink()
        FRAME_FOCUS_DIR.mkdir(parents=True, exist_ok=True)

    def start(self):
        with self.lock:
            if self.running:
                return {"status": "running", "message": "监控已经在运行中"}

            ensure_output_dirs_clean()
            self._load_model()
            self.cap = self._open_video()
            self._reset_state()

            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.duration_seconds = self.total_frames / self.fps if self.fps and self.fps > 0 else 0

            ret, first_frame = self._read_frame_at_second(0.0)
            if not ret or first_frame is None:
                raise RuntimeError("无法读取视频第一帧")
            self.video_height, self.video_width = first_frame.shape[:2]

            self.started_at = time.monotonic()
            self.running = True
            self.worker = threading.Thread(target=self._run_loop, daemon=True)
            self.worker.start()
            return {"status": "ok", "message": "监控已启动"}

    def _run_loop(self):
        frame_index = 0
        second = 0.0

        try:
            while second <= self.duration_seconds:
                while time.monotonic() - self.started_at < second:
                    time.sleep(0.1)

                ret, frame = self._read_frame_at_second(second)
                if not ret or frame is None:
                    break

                frame_index += 1
                frame_record = analyze_frame(
                    model=self.model,
                    pose_utils=self.pose_utils,
                    frame=frame,
                    frame_index=frame_index,
                    timestamp_seconds=second,
                )

                with self.lock:
                    self.frame_records.append(frame_record)
                    self.current_timestamp = second
                    self.events = build_events(self.frame_records)
                    save_event_assets(self.events)
                    for event in self.events:
                        fill_event_data(event, self.current_timestamp, self.completed)
                    self._update_event_ai()
                    self._make_event_map()
                    self._save_files()
                self.ensure_descriptions_async()

                second += FRAME_SEC

            with self.lock:
                self.current_timestamp = min(second, self.duration_seconds)
                self.completed = True
                self.running = False
                for event in self.events:
                    fill_event_data(event, self.current_timestamp, self.completed)
                self._update_event_ai()
                self._make_event_map()
                self._save_files()
        finally:
            if self.cap is not None:
                self.cap.release()
                self.cap = None

    def _save_files(self):
        frame_data = {
            "video_path": str(VIDEO_REL_PATH).replace("\\", "/"),
            "model_name": str(MODEL_PATH),
            "imgsz": IMG_SIZE,
            "conf": CONF,
            "iou": IOU,
            "frame_interval_seconds": FRAME_SEC,
            "fps": self.fps,
            "total_frames": self.total_frames,
            "duration_seconds": round(float(self.duration_seconds), 3),
            "video_width": int(self.video_width),
            "video_height": int(self.video_height),
            "frames": self.frame_records,
        }
        event_data = {
            "video_path": str(VIDEO_REL_PATH).replace("\\", "/"),
            "frame_interval_seconds": FRAME_SEC,
            "event_count": len(self.events),
            "events": self.events,
        }
        save_json(FRAME_JSON_FILE, frame_data)
        save_json(EVENT_JSON_FILE, event_data)
        save_json(DESC_JSON_FILE, self.ai_data)

    def _update_event_ai(self):
        live_ids = {event["event_id"] for event in self.events}
        next_data = {}

        for event in self.events:
            event_id = event["event_id"]
            old_data = self.event_ai.get(event_id, {})
            ai_key = get_ai_key(event_id)
            has_ai = ai_key in self.ai_data["items"]
            next_data[event_id] = {
                "stage": event.get("stage", "candidate"),
                "llm_called": old_data.get("llm_called", False) or has_ai,
            }

        self.event_ai = {
            event_id: item for event_id, item in next_data.items() if event_id in live_ids
        }

    def _make_event_map(self):
        self.event_map = {}
        for event in self.events:
            event_copy = json.loads(json.dumps(event))
            fill_event_data(event_copy, self.current_timestamp, self.completed)
            event_copy["reminder_text"] = remind_text(event_copy["reminder_level"])
            event_copy["summary_text"] = make_event_text(event_copy)

            for crop in event_copy.get("event_crops", []):
                crop["image_path"] = crop["image"]
                crop["image_url"] = to_media_url(crop["image"])
                crop["status_text"] = status_text(crop["status"])
                crop["position_text"] = get_area_text(crop["bbox"], self.video_width, self.video_height)
                ai_key = get_ai_key(event_copy["event_id"])
                ai_item = self.ai_data["items"].get(ai_key, {})
                crop["sit"] = ai_item.get("sit", "")
                crop["action"] = ai_item.get("action", "")
                crop["description"] = ai_item.get("text", "")
                crop["description_error"] = ai_item.get("error", "")

            main_crop = event_copy["event_crops"][0] if event_copy.get("event_crops") else None
            event_copy["list_image_url"] = main_crop["image_url"] if main_crop else ""
            event_copy["list_description"] = main_crop["description"] if main_crop else ""
            event_copy["list_description_error"] = main_crop["description_error"] if main_crop else ""
            if main_crop:
                sit = main_crop.get("sit") or main_crop["position_text"]
                action = main_crop.get("action") or "疑似异常"
                event_copy["list_title"] = f"{sit}，{action}"
            else:
                event_copy["list_title"] = "位置待确认，疑似异常"

            for frame in event_copy["frames"]:
                frame["person"]["status_text"] = status_text(frame["person"]["status"])
                frame["person"]["position_text"] = get_area_text(
                    frame["person"]["bbox"],
                    self.video_width,
                    self.video_height,
                )

            self.event_map[event_copy["event_id"]] = event_copy

    def get_status(self):
        with self.lock:
            event_list = []
            for event in self.events:
                fill_event_data(event, self.current_timestamp, self.completed)
                main_crop = event["event_crops"][0] if event.get("event_crops") else None
                ai_key = ""
                area_text = ""
                if main_crop:
                    ai_key = get_ai_key(event["event_id"])
                    area_text = get_area_text(main_crop["bbox"], self.video_width, self.video_height)

                ai_item = self.ai_data["items"].get(ai_key, {})
                sit = ai_item.get("sit", "") or area_text
                action = ai_item.get("action", "") or "疑似异常"
                event_list.append(
                    {
                        "event_id": event["event_id"],
                        "level": event["level"],
                        "reminder_level": event["reminder_level"],
                        "reminder_text": event["reminder_text"],
                        "stage": event["stage"],
                        "start_time": event["start_time"],
                        "alert_start_time": event["alert_start_time"],
                        "end_time": event["end_time"],
                        "display_time": event["display_time"],
                        "duration_seconds": event["duration_seconds"],
                        "frame_count": event["frame_count"],
                        "peak_ratio": event["peak_ratio"],
                        "summary": make_event_text(event),
                        "list_image_url": to_media_url(main_crop["image"]) if main_crop else "",
                        "list_description": ai_item.get("text", ""),
                        "list_description_error": ai_item.get("error", ""),
                        "list_title": f"{sit}，{action}",
                    }
                )

            return {
                "running": self.running,
                "completed": self.completed,
                "current_timestamp_seconds": round(float(self.current_timestamp), 3),
                "current_time": self.pose_utils.format_time_display(self.current_timestamp),
                "duration_seconds": round(float(self.duration_seconds), 3),
                "duration_time": self.pose_utils.format_time_display(self.duration_seconds),
                "fps": self.fps,
                "frame_interval_seconds": FRAME_SEC,
                "video_width": self.video_width,
                "video_height": self.video_height,
                "video_url": to_media_url(str(VIDEO_REL_PATH).replace("\\", "/")),
                "event_count": len(self.events),
                "events": event_list,
                "model_name": str(MODEL_PATH),
            }

    def get_event_detail(self, event_id: int):
        with self.lock:
            event = self.event_map.get(event_id)
            if event is None:
                raise HTTPException(status_code=404, detail="事件不存在")
            event_data = json.loads(json.dumps(event))

        for frame in event_data["frames"]:
            focus_file = make_frame_focus(event_data["event_id"], frame)
            frame["focus_image_url"] = to_media_url(focus_file) if focus_file else ""

        return event_data

    def generate_description(self, event_id: int, person_id: int):
        with self.lock:
            event = self.event_map.get(event_id)
            if event is None:
                raise HTTPException(status_code=404, detail="事件不存在")

            crop = next((item for item in event.get("event_crops", []) if item["person_id"] == person_id), None)
            if crop is None:
                raise HTTPException(status_code=404, detail="学生截图不存在")

            ai_key = get_ai_key(event_id)
            if ai_key in self.ai_data["items"]:
                cached = self.ai_data["items"][ai_key]
                if "text" not in cached:
                    action = "睡觉" if crop["status"] == "STRONG" else "低头"
                    clean_data = clean_ai_data(
                        cached.get("description", ""),
                        crop.get("position_text") or "位置待确认",
                        action,
                    )
                    cached = {
                        "event_id": event_id,
                        "person_id": person_id,
                        "status": crop["status"],
                        "ratio": crop["ratio"],
                        "sit": clean_data["sit"],
                        "action": clean_data["action"],
                        "text": clean_data["text"],
                    }
                    self.ai_data["items"][ai_key] = cached
                    self.event_ai[event_id] = {
                        "stage": event.get("stage", "active"),
                        "llm_called": True,
                    }
                    self._make_event_map()
                    save_json(DESC_JSON_FILE, self.ai_data)
                return cached

        llm = get_llm()
        response = llm.invoke([make_ai_prompt(event, crop)])
        response_text = response.content.strip() if isinstance(response.content, str) else str(response.content)
        action = "睡觉" if crop["status"] == "STRONG" else "低头"
        clean_data = clean_ai_data(
            response_text,
            crop.get("position_text") or "位置待确认",
            action,
        )

        with self.lock:
            self.ai_data["items"][ai_key] = {
                "event_id": event_id,
                "person_id": person_id,
                "status": crop["status"],
                "ratio": crop["ratio"],
                "sit": clean_data["sit"],
                "action": clean_data["action"],
                "text": clean_data["text"],
            }
            self.event_ai[event_id] = {
                "stage": event.get("stage", "active"),
                "llm_called": True,
            }
            self._make_event_map()
            save_json(DESC_JSON_FILE, self.ai_data)
            return self.ai_data["items"][ai_key]

    def ensure_descriptions_async(self):
        jobs = []
        with self.lock:
            for event in self.event_map.values():
                if event.get("stage") != "active":
                    continue

                crops = event.get("event_crops", [])
                if not crops:
                    continue

                crop = crops[0]
                event_ai = self.event_ai.get(event["event_id"], {})
                ai_key = get_ai_key(event["event_id"])
                if ai_key in self.ai_data["items"]:
                    continue
                if ai_key in self.wait_keys:
                    continue
                if event_ai.get("llm_called"):
                    continue

                self.wait_keys.add(ai_key)
                jobs.append((event["event_id"], crop["person_id"], ai_key))

        for event_id, person_id, ai_key in jobs:
            threading.Thread(
                target=self._generate_description_worker,
                args=(event_id, person_id, ai_key),
                daemon=True,
            ).start()

    def _generate_description_worker(self, event_id: int, person_id: int, ai_key: str):
        try:
            self.generate_description(event_id, person_id)
        except Exception as exc:
            print(f"[LLM] 事件 {event_id} 描述生成失败: {exc}", flush=True)
            with self.lock:
                self.ai_data["items"][ai_key] = {
                    "event_id": event_id,
                    "person_id": person_id,
                    "error": "模型调用失败",
                }
                self.event_ai[event_id] = {
                    "stage": self.event_map.get(event_id, {}).get("stage", "active"),
                    "llm_called": True,
                }
                self._make_event_map()
                save_json(DESC_JSON_FILE, self.ai_data)
        finally:
            with self.lock:
                self.wait_keys.discard(ai_key)


engine = MonitorEngine()
app = FastAPI(title="Classroom Monitor Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=str(ROOT_DIR)), name="media")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/monitor/start", response_model=StartResponse)
def start_monitor():
    try:
        result = engine.start()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@app.get("/api/monitor/status")
def monitor_status():
    return engine.get_status()


@app.get("/api/events/{event_id}")
def event_detail(event_id: int):
    return engine.get_event_detail(event_id)


@app.post("/api/events/{event_id}/persons/{person_id}/describe")
def describe_person(event_id: int, person_id: int):
    try:
        return engine.generate_description(event_id, person_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
