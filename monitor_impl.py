import os
import json
import base64
import time
import cv2
import queue
import numpy as np
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from video_stream_util import MockMonitorStream
from pose_engine import PoseEngine

ROOT_PATH = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_PATH / "outputs/final"
EVENT_CROP_DIR = OUTPUT_DIR / "event_crops"
LOG_DIR = OUTPUT_DIR / "analysis_logs"
REVIEW_INPUT_DIR = OUTPUT_DIR / "review_inputs"

EVENT_CROP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
REVIEW_INPUT_DIR.mkdir(parents=True, exist_ok=True)

video_stream = MockMonitorStream()
initial_frame = video_stream.get_latest_frame()

_cap_info = cv2.VideoCapture(str(ROOT_PATH / "inputs/video/test.mp4"))
IMG_W = int(_cap_info.get(cv2.CAP_PROP_FRAME_WIDTH))
IMG_H = int(_cap_info.get(cv2.CAP_PROP_FRAME_HEIGHT))
_cap_info.release()

state = {
    "is_running": False,
    "time": "00:00:00",
    "frame": initial_frame,
    "img_w": IMG_W,
    "img_h": IMG_H,
    "seats": [],
    "events": [],
    "counts": {
        "total": 0,
        "focus": 0,
        "normal": 0
    }
}

websocket_clients = set()
review_queue = queue.Queue(maxsize=2)
review_last_at = {}
SUSPECT_CONFIRM_COUNT = 2
REVIEW_COOLDOWN_SECONDS = 15
REVIEW_CROP_PAD = 8
EVENT_CROP_PAD = 20
RECOVER_CONFIRM_COUNT = 2

def box_center(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

def box_distance_sq(box_a, box_b):
    ax, ay = box_center(box_a)
    bx, by = box_center(box_b)
    return (ax - bx) ** 2 + (ay - by) ** 2

def box_iou(box_a, box_b):
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0

def can_match_track(track_box, det_box):
    dist_sq = box_distance_sq(track_box, det_box)
    iou = box_iou(track_box, det_box)
    width = max(1, track_box[2] - track_box[0])
    height = max(1, track_box[3] - track_box[1])
    return iou >= 0.08 or dist_sq < max(3000, (max(width, height) * 0.8) ** 2)

def track_match_score(track_box, det_box):
    return box_iou(track_box, det_box) * 10000 - box_distance_sq(track_box, det_box)

def find_current_seat(ans, review_seats):
    target_id = ans.get("seat_id")
    review_seat = next((s for s in review_seats if s["seat_id"] == target_id), None)

    for s in state["seats"]:
        if s["seat_id"] == target_id:
            return s, review_seat or s

    if review_seat:
        for s in state["seats"]:
            if s["seat_code"] == review_seat["seat_code"]:
                return s, review_seat

        nearest = None
        nearest_dist = None
        for s in state["seats"]:
            dist = box_distance_sq(s["box"], review_seat["box"])
            if nearest_dist is None or dist < nearest_dist:
                nearest = s
                nearest_dist = dist
        if nearest is not None and nearest_dist < 9000:
            return nearest, review_seat

    return None, review_seat

def build_review_sheet(frame, seats):
    cell_w, cell_h = 320, 240
    cols = min(3, len(seats))
    rows = (len(seats) + cols - 1) // cols
    sheet = 255 * np.ones((rows * cell_h, cols * cell_w, 3), dtype="uint8")
    targets_text = ""
    h, w = frame.shape[:2]

    for i, s in enumerate(seats):
        bx = s["box"]
        x1, x2 = max(0, int(bx[0]) - REVIEW_CROP_PAD), min(w, int(bx[2]) + REVIEW_CROP_PAD)
        y1, y2 = max(0, int(bx[1]) - REVIEW_CROP_PAD), min(h, int(bx[3]) + REVIEW_CROP_PAD)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        scale = min((cell_w - 20) / crop.shape[1], (cell_h - 42) / crop.shape[0])
        resized_w = max(1, int(crop.shape[1] * scale))
        resized_h = max(1, int(crop.shape[0] * scale))
        resized = cv2.resize(crop, (resized_w, resized_h))
        row, col = divmod(i, cols)
        top = row * cell_h + 34
        left = col * cell_w + 10
        sheet[top:top + resized_h, left:left + resized_w] = resized
        label = f"seat_id:{s['seat_id']} {s['seat_code']}"
        cv2.putText(sheet, label, (col * cell_w + 10, row * cell_h + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
        targets_text += f"- seat_id: {s['seat_id']}, code: {s['seat_code']}, crop_label: {label}\n"

    return sheet, targets_text

def parse_model_json(response):
    content = response.strip().strip("```json").strip("```").strip()
    if not content.startswith("["):
        start = content.find("[")
        end = content.rfind("]")
        if start >= 0 and end > start:
            content = content[start:end + 1]
    return json.loads(content)

def apply_review_result(response, answers, frame, review_seats, ts_ms, input_image_path):
    with open(LOG_DIR / f"audit_{ts_ms}.json", "w", encoding="utf-8") as f_log:
        json.dump({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "input_image": str(input_image_path),
            "raw": response
        }, f_log, ensure_ascii=False, indent=2)

    for ans in answers:
        s_obj, review_seat = find_current_seat(ans, review_seats)
        target = s_obj or review_seat
        if not target:
            continue

        if s_obj:
            s_obj["status"] = ans["status"]
            if ans["status"] in ["HEAD_DOWN", "DESK_LYING"]:
                s_obj["locked_abnormal"] = True
            else:
                s_obj["locked_abnormal"] = False

        if ans["status"] in ["HEAD_DOWN", "DESK_LYING"]:
            file_name = f"ev_{ts_ms}_{target['seat_code']}.jpg"
            bx = target["box"]
            y1, y2 = max(0, int(bx[1])-EVENT_CROP_PAD), min(state["img_h"], int(bx[3])+EVENT_CROP_PAD)
            x1, x2 = max(0, int(bx[0])-EVENT_CROP_PAD), min(state["img_w"], int(bx[2])+EVENT_CROP_PAD)
            cv2.imwrite(str(EVENT_CROP_DIR / file_name), frame[y1:y2, x1:x2])
            state["events"].insert(0, {
                "id": time.time(),
                "time": time.strftime("%H:%M:%S"),
                "seat": target["seat_code"],
                "label": ans["label"],
                "reason": ans["reason"],
                "risk": "高" if ans["risk_level"]=="HIGH" else "中",
                "url": f"/event_crops/{file_name}",
                "full_ans": response,
                "box": bx
            })

def enqueue_review(frame, seats):
    now = time.time()
    targets = []
    for s in seats:
        last_at = review_last_at.get(s["seat_id"], 0)
        if now - last_at >= REVIEW_COOLDOWN_SECONDS:
            targets.append(dict(s))

    if not targets:
        return

    try:
        review_queue.put_nowait({
            "frame": frame.copy(),
            "seats": targets
        })
        for s in targets:
            review_last_at[s["seat_id"]] = now
    except queue.Full:
        pass

def vlm_review_worker():
    vlm_client = ChatOpenAI(
        model="qwen-vl-max",
        api_key=os.environ.get("ALIYUN_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    sys_prompt_content = (ROOT_PATH / "vlm_system_prompt.md").read_text(encoding="utf-8")
    usr_prompt_tmpl = (ROOT_PATH / "vlm_user_prompt.md").read_text(encoding="utf-8")

    while True:
        job = review_queue.get()
        if not state["is_running"]:
            continue

        try:
            sheet, targets_text = build_review_sheet(job["frame"], job["seats"])
            ts_ms = int(time.time() * 1000)
            input_image_path = REVIEW_INPUT_DIR / f"review_{ts_ms}.jpg"
            cv2.imwrite(str(input_image_path), sheet)
            success, buffer = cv2.imencode('.jpg', sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not success:
                continue
            img_b64 = base64.b64encode(buffer).decode('utf-8')
            user_msg = usr_prompt_tmpl.replace("{{targets_info}}", targets_text)
            response = vlm_client.invoke([
                SystemMessage(content=sys_prompt_content),
                HumanMessage(
                    content=[
                        {"type": "text", "text": user_msg},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                        }
                    ]
                )
            ]).content
            if state["is_running"]:
                apply_review_result(response, parse_model_json(response), job["frame"], job["seats"], ts_ms, input_image_path)
        except Exception as e:
            print(f"智能复核环节异常：{e}")

def detection_analysis_loop():
    print("智能识别引擎正在初始化...")

    detector = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(ROOT_PATH / "models" / "detect.pt"),
        confidence_threshold=0.25
    )

    pose_model = PoseEngine(str(ROOT_PATH / "models" / "yolo26s-pose.pt"))
    
    cycle_index = 0
    seat_id_counter = 100
    suspect_hits = {}
    recover_hits = {}

    while True:
        if not state["is_running"]:
            time.sleep(0.5)
            continue

        current_frame = state["frame"]
        if current_frame is None:
            continue

        prediction = get_sliced_prediction(
            current_frame,
            detector,
            slice_height=640,
            slice_width=640,
            verbose=0
        )
        
        detections = [p for p in prediction.object_prediction_list if p.category.id == 0]
        new_tracked_seats = []
        used_seat_ids = set()

        for det in detections:
            raw_box = det.bbox.to_xyxy()
            box_xyxy = [
                round(raw_box[0], 2),
                round(raw_box[1], 2),
                round(raw_box[2], 2),
                round(raw_box[3], 2)
            ]

            matched = None
            best_dist = None
            for s in state["seats"]:
                if s["seat_id"] in used_seat_ids:
                    continue
                dist_sq = box_distance_sq(box_xyxy, s["box"])
                if dist_sq < 3000 and (best_dist is None or dist_sq < best_dist):
                    matched = s
                    best_dist = dist_sq

            if matched:
                used_seat_ids.add(matched["seat_id"])
                matched["box"] = box_xyxy
                new_tracked_seats.append(matched)
            else:
                if any(box_distance_sq(box_xyxy, s["box"]) < 1200 for s in new_tracked_seats):
                    continue
                seat_id_counter += 1
                new_tracked_seats.append({
                    "seat_id": seat_id_counter,
                    "seat_code": f"S{seat_id_counter - 100:02d}",
                    "box": box_xyxy,
                    "status": "NORMAL",
                    "locked_abnormal": False
                })
        
        new_tracked_seats.sort(key=lambda item: item["seat_id"])
        state["seats"] = new_tracked_seats

        if cycle_index % 3 == 0 and state["seats"]:
            poses = pose_model.detect_poses_batch(current_frame, state["seats"])
            suspected = []
            
            for i, (p_status, _) in enumerate(poses):
                if i >= len(state["seats"]):
                    break
                s = state["seats"][i]
                if p_status in ["SUSPECTED", "UNCERTAIN"]:
                    suspect_hits[s["seat_id"]] = suspect_hits.get(s["seat_id"], 0) + 1
                    recover_hits[s["seat_id"]] = 0
                    if suspect_hits[s["seat_id"]] >= SUSPECT_CONFIRM_COUNT:
                        suspected.append(s)
                else:
                    suspect_hits[s["seat_id"]] = 0
                    if not s.get("locked_abnormal"):
                        s["status"] = p_status
                    else:
                        recover_hits[s["seat_id"]] = recover_hits.get(s["seat_id"], 0) + 1
                        if recover_hits[s["seat_id"]] >= RECOVER_CONFIRM_COUNT:
                            s["locked_abnormal"] = False
                            s["status"] = p_status

            if suspected:
                enqueue_review(current_frame, suspected)

        state["time"] = time.strftime("%H:%M:%S")

        state["counts"] = {
            "total": len(state["seats"]),
            "focus": sum(1 for e in state["events"] if e["risk"] == "高"),
            "normal": sum(1 for e in state["events"] if e["risk"] == "中")
        }

        cycle_index += 1
        time.sleep(0.1)

def frame_loader_worker():
    while True:
        state["frame"] = video_stream.get_latest_frame()
        time.sleep(0.04)
