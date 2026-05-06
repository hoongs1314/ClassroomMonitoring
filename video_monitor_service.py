import json
import os
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

from pose_utils import PoseDebugUtils
from video_pose_debug import (
    CONF,
    EVENT_JSON_PATH,
    EVENT_OUTPUT_DIR,
    FRAME_INTERVAL_SECONDS,
    FRAME_JSON_PATH,
    IMG_SIZE,
    IOU,
    MODEL_NAME,
    OUTPUT_DIR,
    POSE_CONFIG,
    VIDEO_PATH,
    analyze_frame,
    build_events,
    ensure_output_dirs_clean,
    save_event_assets,
)

BASE_DIR = Path(__file__).resolve().parent
VIDEO_FILE_PATH = BASE_DIR / VIDEO_PATH
DESCRIPTION_JSON_PATH = OUTPUT_DIR / "event_descriptions.json"
DEFAULT_QWEN_MODEL = os.getenv("QWEN_VL_MODEL", "qwen3-vl-plus")
DEFAULT_DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)


class StartResponse(BaseModel):
    status: str
    message: str


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_media_url(path_str: str) -> str:
    normalized = path_str.replace("\\", "/").lstrip("/")
    return f"/media/{normalized}"


def image_to_data_url(image_path: str) -> str:
    import base64

    suffix = Path(image_path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    image_bytes = Path(image_path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"


def build_description_prompt(event: dict, crop: dict) -> HumanMessage:
    return HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "你在看教室监控中的单个学生异常截图。"
                    "请输出 2 句以内的中文描述。"
                    "第一句描述学生当前动作和姿态。"
                    "第二句说明为什么它会被当成疑似异常。"
                    "如果更像正常低头学习，也请直接指出。"
                    f" 当前事件级别：{event['level']}。"
                    f" 当前检测状态：{crop['status']}。"
                    f" 当前比例值：{crop['ratio']}。"
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": image_to_data_url(crop["image_path"])},
            },
        ]
    )


def get_llm() -> ChatOpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY，无法生成异常描述。")

    return ChatOpenAI(
        model=DEFAULT_QWEN_MODEL,
        api_key=api_key,
        base_url=DEFAULT_DASHSCOPE_BASE_URL,
        temperature=0.1,
    )


class MonitorEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.pose_utils = PoseDebugUtils(POSE_CONFIG)
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
        self.description_store = load_json(DESCRIPTION_JSON_PATH) or {"items": {}}

    def _load_model(self):
        if self.model is None:
            self.model = YOLO(MODEL_NAME)

    def _open_video(self):
        cap = cv2.VideoCapture(str(VIDEO_FILE_PATH))
        if not cap.isOpened():
            raise RuntimeError(f"视频打开失败：{VIDEO_FILE_PATH}")
        return cap

    def _read_frame_at_second(self, timestamp_seconds: float):
        if self.cap is None:
            return False, None
        if self.fps <= 0:
            self.cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000)
        else:
            target_frame_index = int(round(timestamp_seconds * self.fps))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_index)
        return self.cap.read()

    def _reset_state(self):
        self.completed = False
        self.current_timestamp = 0.0
        self.frame_records = []
        self.events = []
        self.event_map = {}

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
        timestamp_seconds = 0.0

        try:
            while timestamp_seconds <= self.duration_seconds:
                while time.monotonic() - self.started_at < timestamp_seconds:
                    time.sleep(0.1)

                ret, frame = self._read_frame_at_second(timestamp_seconds)
                if not ret or frame is None:
                    break

                frame_index += 1
                frame_record = analyze_frame(
                    model=self.model,
                    pose_utils=self.pose_utils,
                    frame=frame,
                    frame_index=frame_index,
                    timestamp_seconds=timestamp_seconds,
                )

                with self.lock:
                    self.frame_records.append(frame_record)
                    self.current_timestamp = timestamp_seconds
                    self.events = build_events(self.frame_records)
                    save_event_assets(self.events)
                    self._sync_event_descriptions()
                    self._refresh_event_map()
                    self._persist_outputs()

                timestamp_seconds += FRAME_INTERVAL_SECONDS

            with self.lock:
                self.current_timestamp = min(timestamp_seconds, self.duration_seconds)
                self.completed = True
                self.running = False
                self._persist_outputs()
        finally:
            if self.cap is not None:
                self.cap.release()
                self.cap = None

    def _persist_outputs(self):
        frame_results = {
            "video_path": str(VIDEO_PATH).replace("\\", "/"),
            "model_name": MODEL_NAME,
            "imgsz": IMG_SIZE,
            "conf": CONF,
            "iou": IOU,
            "frame_interval_seconds": FRAME_INTERVAL_SECONDS,
            "fps": self.fps,
            "total_frames": self.total_frames,
            "duration_seconds": round(float(self.duration_seconds), 3),
            "video_width": int(self.video_width),
            "video_height": int(self.video_height),
            "frames": self.frame_records,
        }
        event_results = {
            "video_path": str(VIDEO_PATH).replace("\\", "/"),
            "frame_interval_seconds": FRAME_INTERVAL_SECONDS,
            "event_count": len(self.events),
            "events": self.events,
        }
        save_json(FRAME_JSON_PATH, frame_results)
        save_json(EVENT_JSON_PATH, event_results)
        save_json(DESCRIPTION_JSON_PATH, self.description_store)

    def _refresh_event_map(self):
        self.event_map = {}
        for event in self.events:
            event_copy = json.loads(json.dumps(event))
            event_copy["event_debug_image_url"] = to_media_url(event["event_debug_image"]) if event["event_debug_image"] else ""
            event_copy["event_raw_image_url"] = to_media_url(event["event_raw_image"]) if event["event_raw_image"] else ""
            for crop in event_copy.get("event_crops", []):
                crop["image_path"] = crop["image"]
                crop["image_url"] = to_media_url(crop["image"])
                cache_key = f"event_{event_copy['event_id']}_person_{crop['person_id']}"
                crop["description"] = self.description_store["items"].get(cache_key, {}).get("description", "")
            for frame in event_copy["frames"]:
                frame["debug_image_url"] = to_media_url(frame["debug_image"])
                frame["raw_frame_url"] = to_media_url(frame["raw_frame"])
            self.event_map[event_copy["event_id"]] = event_copy

    def _sync_event_descriptions(self):
        if not DESCRIPTION_JSON_PATH.exists():
            return
        self.description_store = load_json(DESCRIPTION_JSON_PATH) or {"items": {}}

    def get_status(self):
        with self.lock:
            event_summaries = []
            for event in self.events:
                event_summaries.append(
                    {
                        "event_id": event["event_id"],
                        "level": event["level"],
                        "start_time": event["start_time"],
                        "end_time": event["end_time"],
                        "duration_seconds": event["duration_seconds"],
                        "frame_count": event["frame_count"],
                        "peak_ratio": event["peak_ratio"],
                        "summary": event["summary"],
                        "event_debug_image_url": to_media_url(event["event_debug_image"]) if event["event_debug_image"] else "",
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
                "frame_interval_seconds": FRAME_INTERVAL_SECONDS,
                "video_width": self.video_width,
                "video_height": self.video_height,
            "video_url": to_media_url(str(VIDEO_PATH).replace("\\", "/")),
                "event_count": len(self.events),
                "events": event_summaries,
                "model_name": MODEL_NAME,
            }

    def get_event_detail(self, event_id: int):
        with self.lock:
            event = self.event_map.get(event_id)
            if event is None:
                raise HTTPException(status_code=404, detail="事件不存在")
            return event

    def generate_description(self, event_id: int, person_id: int):
        with self.lock:
            event = self.event_map.get(event_id)
            if event is None:
                raise HTTPException(status_code=404, detail="事件不存在")
            crop = next((item for item in event.get("event_crops", []) if item["person_id"] == person_id), None)
            if crop is None:
                raise HTTPException(status_code=404, detail="学生截图不存在")
            cache_key = f"event_{event_id}_person_{person_id}"
            if cache_key in self.description_store["items"]:
                return self.description_store["items"][cache_key]

        llm = get_llm()
        response = llm.invoke([build_description_prompt(event, crop)])
        description = response.content.strip() if isinstance(response.content, str) else str(response.content)

        with self.lock:
            self.description_store["items"][cache_key] = {
                "event_id": event_id,
                "person_id": person_id,
                "status": crop["status"],
                "ratio": crop["ratio"],
                "description": description,
            }
            self._refresh_event_map()
            save_json(DESCRIPTION_JSON_PATH, self.description_store)
            return self.description_store["items"][cache_key]


engine = MonitorEngine()
app = FastAPI(title="Classroom Monitor Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=str(BASE_DIR)), name="media")


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
