import json
import threading
import time
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ultralytics import YOLO

from config import (
    DETAIL_DIR,
    DETECT_MODEL,
    EVENT_JSON_FILE,
    FRAME_JSON_FILE,
    FRAME_SEC,
    POSE_MODEL,
    POSE_RULE,
    ROOT_DIR,
    SEAT_JSON_FILE,
    SEAT_MAP_FILE,
    VIDEO_FILE,
    VIDEO_REL_PATH,
    make_dirs,
)
from pose_utils import PoseDebugUtils
from video_pose import (
    analyze_frame,
    build_events,
    build_seats,
    clear_out,
    expand_box,
    read_frame_at,
    save_event_assets,
    save_seat_map_image,
)

make_dirs()


class StartResponse(BaseModel):
    status: str
    message: str


STATUS_TEXT = {
    "EMPTY": "空位",
    "NORMAL": "正常",
    "WEAK": "轻度异常",
    "STRONG": "明显异常",
    "INVALID": "关键点不足",
}

REMIND_TEXT = {
    "FOCUS": "重点提醒",
    "NORMAL": "普通提醒",
}

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def media_url(path_str: str) -> str:
    file_path = path_str.replace("\\", "/").lstrip("/")
    return f"/media/{file_path}"


def fill_event(event: dict):
    # 展示字段
    keep = 0
    best = 0
    for frame in event.get("frames", []):
        if frame["seat"]["status"] == "STRONG":
            keep += 1
            best = max(best, keep)
        else:
            keep = 0
    level = "FOCUS" if best >= 3 else "NORMAL"
    for frame in event.get("frames", []):
        if frame["seat"]["status"] == event["level"]:
            start_time = frame["time"]
            start_sec = frame["timestamp_seconds"]
            break
    else:
        start_time = event["start_time"]
        start_sec = event["start_timestamp_seconds"]

    event["alert_start_time"] = start_time
    event["alert_start_seconds"] = start_sec
    event["reminder_level"] = level
    event["reminder_text"] = REMIND_TEXT.get(level, level)
    event["summary_text"] = (
        f"{event['seat_name']}，{event['reminder_text']}，"
        f"{start_time} 到 {event['end_time']}，"
        f"持续 {event['duration_seconds']} 秒。"
    )


def make_detail_crop(event_id: int, frame: dict) -> str:
    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DETAIL_DIR / f"event_{event_id:03d}_frame_{frame['frame_index']:06d}_seat_{frame['seat']['seat_id']:03d}.jpg"
    if file_path.exists():
        return str(file_path.relative_to(ROOT_DIR)).replace("\\", "/")

    raw_file = ROOT_DIR / frame["raw_frame"]
    raw_img = cv2.imread(str(raw_file))
    if raw_img is None:
        return ""

    image_h, image_w = raw_img.shape[:2]
    seat_box = frame["seat"]["seat_box"]
    cut_x1, cut_y1, cut_x2, cut_y2 = expand_box(seat_box, image_w, image_h, 0.28)
    if cut_x2 <= cut_x1 or cut_y2 <= cut_y1:
        return ""

    crop = raw_img[cut_y1:cut_y2, cut_x1:cut_x2].copy()
    sx1, sy1, sx2, sy2 = [int(round(v)) for v in seat_box]
    seat_layer = crop.copy()
    cv2.rectangle(seat_layer, (sx1 - cut_x1, sy1 - cut_y1), (sx2 - cut_x1, sy2 - cut_y1), (180, 150, 70), 1)
    crop = cv2.addWeighted(seat_layer, 0.35, crop, 0.65, 0)

    person_box = frame["seat"].get("person_box")
    if person_box:
        px1, py1, px2, py2 = [int(round(v)) for v in person_box]
        color = (0, 0, 255) if frame["seat"]["status"] == "STRONG" else (0, 255, 255)
        cv2.rectangle(crop, (px1 - cut_x1, py1 - cut_y1), (px2 - cut_x1, py2 - cut_y1), color, 2)
    cv2.imwrite(str(file_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return str(file_path.relative_to(ROOT_DIR)).replace("\\", "/")


class MonitorEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.pose_utils = PoseDebugUtils(POSE_RULE)
        self.detect_model = None
        self.pose_model = None
        self.cap = None
        self.worker = None
        self.running = False
        self.completed = False
        self.phase = "idle"
        self.error = ""
        self.started_at = 0.0
        self.current_seconds = 0.0
        self.duration_seconds = 0.0
        self.fps = 0.0
        self.total_frames = 0
        self.video_width = 0
        self.video_height = 0
        self.seats = []
        self.seat_map_file = ""
        self.frame_records = []
        self.events = []
        self.event_map = {}

    def _reset(self):
        self.completed = False
        self.phase = "idle"
        self.error = ""
        self.current_seconds = 0.0
        self.seats = []
        self.seat_map_file = ""
        self.frame_records = []
        self.events = []
        self.event_map = {}
        DETAIL_DIR.mkdir(parents=True, exist_ok=True)

    def start(self):
        with self.lock:
            if self.running:
                return {"status": "running", "message": "监控已经在运行中"}

            clear_out()
            if self.detect_model is None:
                self.detect_model = YOLO(str(DETECT_MODEL))
            if self.pose_model is None:
                self.pose_model = YOLO(str(POSE_MODEL))

            self.cap = cv2.VideoCapture(str(VIDEO_FILE))
            if not self.cap.isOpened():
                raise RuntimeError(f"视频打开失败：{VIDEO_FILE}")
            self._reset()

            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.duration_seconds = self.total_frames / self.fps if self.fps and self.fps > 0 else 0

            ret, first_frame = read_frame_at(self.cap, self.fps, 0.0)
            if not ret or first_frame is None:
                raise RuntimeError("无法读取视频第一帧")
            self.video_height, self.video_width = first_frame.shape[:2]

            self.started_at = time.monotonic()
            self.running = True
            self.phase = "init"
            self.worker = threading.Thread(target=self._run_loop, daemon=True)
            self.worker.start()
            print(
                f"[monitor] started: video={VIDEO_REL_PATH}, fps={self.fps:.2f}, "
                f"frames={self.total_frames}, duration={self.duration_seconds:.2f}s",
                flush=True,
            )
            return {"status": "ok", "message": "监控已启动，正在识别座位"}

    def _run_loop(self):
        try:
            with self.lock:
                self.phase = "init"
            print("[monitor] phase=init, building seats", flush=True)
            # 先建座位图
            seats = build_seats(self.detect_model, self.cap, self.fps, self.duration_seconds)
            ret, seat_frame = read_frame_at(self.cap, self.fps, 0.0)
            seat_map_file = save_seat_map_image(seat_frame, seats, SEAT_MAP_FILE) if ret else ""

            with self.lock:
                self.seats = seats
                self.seat_map_file = seat_map_file
                save_json(
                    SEAT_JSON_FILE,
                    {
                        "video_path": str(VIDEO_REL_PATH).replace("\\", "/"),
                        "seat_count": len(seats),
                        "seat_map": seat_map_file,
                        "seats": seats,
                    },
                )
                self.phase = "monitor"
                print(f"[monitor] phase=monitor, seat_count={len(seats)}, seat_map={seat_map_file}", flush=True)

            frame_index = 0
            sec = 0.0
            while sec <= self.duration_seconds:
                # 跟随视频时间
                while time.monotonic() - self.started_at < sec:
                    time.sleep(0.08)

                ret, frame = read_frame_at(self.cap, self.fps, sec)
                if not ret or frame is None:
                    break

                frame_index += 1
                frame_record = analyze_frame(
                    pose_model=self.pose_model,
                    pose_utils=self.pose_utils,
                    frame=frame,
                    frame_index=frame_index,
                    sec=sec,
                    seats=self.seats,
                )

                with self.lock:
                    # 刷新结果
                    self.current_seconds = sec
                    self.frame_records.append(frame_record)
                    self.events = build_events(self.frame_records)
                    save_event_assets(self.events)
                    for event in self.events:
                        fill_event(event)
                    self._make_event_map()
                    self._save_files()
                    print(
                        f"[monitor] frame={frame_index}, time={frame_record['time']}, events={len(self.events)}",
                        flush=True,
                    )

                sec += FRAME_SEC

            with self.lock:
                self.current_seconds = min(sec, self.duration_seconds)
                self.completed = True
                self.running = False
                self.phase = "done"
                for event in self.events:
                    fill_event(event)
                self._make_event_map()
                self._save_files()
                print(f"[monitor] phase=done, frames={len(self.frame_records)}, events={len(self.events)}", flush=True)
        except Exception as exc:
            with self.lock:
                self.running = False
                self.completed = False
                self.phase = "error"
                self.error = str(exc)
            print(f"[monitor] error: {exc}", flush=True)
        finally:
            if self.cap is not None:
                self.cap.release()
                self.cap = None

    def _save_files(self):
        save_json(
            FRAME_JSON_FILE,
            {
                "video_path": str(VIDEO_REL_PATH).replace("\\", "/"),
                "frame_interval_seconds": FRAME_SEC,
                "seat_count": len(self.seats),
                "seat_map": self.seat_map_file,
                "frames": self.frame_records,
            },
        )
        save_json(
            EVENT_JSON_FILE,
            {
                "video_path": str(VIDEO_REL_PATH).replace("\\", "/"),
                "seat_count": len(self.seats),
                "event_count": len(self.events),
                "seat_map": self.seat_map_file,
                "events": self.events,
            },
        )

    def _make_event_map(self):
        self.event_map = {}
        for event in self.events:
            item = json.loads(json.dumps(event))
            fill_event(item)
            for crop in item.get("event_crops", []):
                crop["image_path"] = crop["image"]
                crop["image_url"] = media_url(crop["image"])
                crop["status_text"] = STATUS_TEXT.get(crop["status"], crop["status"])
                crop["action"] = "睡觉" if item["level"] == "STRONG" else "低头"

            main_crop = item["event_crops"][0] if item.get("event_crops") else None
            item["list_image_url"] = main_crop["image_url"] if main_crop else ""
            if main_crop:
                item["list_title"] = f"{item['seat_name']}，{main_crop['action']}"
            else:
                item["list_title"] = f"{item['seat_name']}，疑似异常"

            for frame in item["frames"]:
                frame["seat"]["status_text"] = STATUS_TEXT.get(frame["seat"]["status"], frame["seat"]["status"])

            self.event_map[item["event_id"]] = item

    def get_status(self):
        with self.lock:
            if self.running and self.started_at:
                show_seconds = min(self.duration_seconds, max(0.0, time.monotonic() - self.started_at))
            else:
                show_seconds = self.current_seconds

            events = []
            for event in self.events:
                fill_event(event)
                action = "睡觉" if event["level"] == "STRONG" else "低头"
                crop = event["event_crops"][0] if event.get("event_crops") else None
                events.append(
                    {
                        "event_id": event["event_id"],
                        "seat_id": event["seat_id"],
                        "seat_name": event["seat_name"],
                        "level": event["level"],
                        "reminder_level": event["reminder_level"],
                        "reminder_text": event["reminder_text"],
                        "start_time": event["start_time"],
                        "alert_start_time": event["alert_start_time"],
                        "end_time": event["end_time"],
                        "duration_seconds": event["duration_seconds"],
                        "peak_ratio": event["peak_ratio"],
                        "list_title": f"{event['seat_name']}，{action}",
                        "list_image_url": media_url(crop["image"]) if crop else "",
                    }
                )

            return {
                "running": self.running,
                "completed": self.completed,
                "phase": self.phase,
                "error": self.error,
                "current_seconds": round(float(show_seconds), 3),
                "current_time": self.pose_utils.format_time_display(show_seconds),
                "analyze_seconds": round(float(self.current_seconds), 3),
                "analyze_time": self.pose_utils.format_time_display(self.current_seconds),
                "duration_seconds": round(float(self.duration_seconds), 3),
                "duration_time": self.pose_utils.format_time_display(self.duration_seconds),
                "frame_interval_seconds": FRAME_SEC,
                "seat_count": len(self.seats),
                "event_count": len(self.events),
                "seat_map_url": media_url(self.seat_map_file) if self.seat_map_file else "",
                "seats": self.seats,
                "events": events,
                "video_url": media_url(str(VIDEO_REL_PATH).replace("\\", "/")),
                "detect_model": str(DETECT_MODEL.name),
                "pose_model": str(POSE_MODEL.name),
            }

    def get_event_detail(self, event_id: int):
        with self.lock:
            event = self.event_map.get(event_id)
            if event is None:
                raise HTTPException(status_code=404, detail="事件不存在")
            data = json.loads(json.dumps(event))

        for frame in data["frames"]:
            focus_file = make_detail_crop(data["event_id"], frame)
            frame["focus_image_url"] = media_url(focus_file) if focus_file else ""
        return data


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
        return engine.start()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/monitor/status")
def monitor_status():
    return engine.get_status()


@app.get("/api/events/{event_id}")
def event_detail(event_id: int):
    return engine.get_event_detail(event_id)
