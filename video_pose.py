import json
import shutil
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from config import (
    CROP_DIR,
    DETECT_CONF,
    DETECT_IOU,
    DETECT_MODEL,
    DETAIL_DIR,
    EVENT_DIR,
    EVENT_END_NORMAL_FRAMES,
    EVENT_JSON_FILE,
    EVENT_START_STRONG_FRAMES,
    EVENT_START_WEAK_FRAMES,
    FRAME_JSON_FILE,
    FRAME_SEC,
    IMG_SIZE,
    OUT_DIR,
    POSE_CONF,
    POSE_IOU,
    POSE_MIN_SEAT_OVERLAP,
    POSE_MODEL,
    POSE_RULE,
    RAW_DIR,
    ROOT_DIR,
    SEAT_FRAME_COUNT,
    SEAT_CROP_PAD,
    SEAT_IMG_SIZE,
    SEAT_JSON_FILE,
    SEAT_MAP_FILE,
    SEAT_SEC,
    VIDEO_FILE,
    VIDEO_REL_PATH,
    make_dirs,
)
from pose_utils import PoseDebugUtils

make_dirs()


def clear_out():
    for path in [RAW_DIR, EVENT_DIR]:
        if not path.exists():
            continue
        for child in path.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    CROP_DIR.mkdir(parents=True, exist_ok=True)
    DETAIL_DIR.mkdir(parents=True, exist_ok=True)


def read_frame_at(cap, fps: float, sec: float):
    if fps <= 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
    else:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(sec * fps)))
    return cap.read()


def box_center(box: list[float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def box_overlap_ratio(box1: list[float], box2: list[float]) -> float:
    # 绑定座位
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    small_area = min(area1, area2)
    if small_area <= 0:
        return 0.0
    return inter / small_area


def same_box(box1: list[float], box2: list[float]) -> bool:
    x1, y1 = box_center(box1)
    x2, y2 = box_center(box2)
    w = max(40.0, min(box1[2] - box1[0], box2[2] - box2[0]))
    h = max(60.0, min(box1[3] - box1[1], box2[3] - box2[1]))
    return abs(x1 - x2) <= w * 0.7 and abs(y1 - y2) <= h * 0.8


def avg_box(box_list: list[list[float]]) -> list[float]:
    size = len(box_list)
    return [
        round(sum(box[0] for box in box_list) / size, 2),
        round(sum(box[1] for box in box_list) / size, 2),
        round(sum(box[2] for box in box_list) / size, 2),
        round(sum(box[3] for box in box_list) / size, 2),
    ]


def expand_box(box: list[float], image_w: int, image_h: int, pad: float = 0.22) -> list[int]:
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    pad_x = w * pad
    pad_y = h * pad
    return [
        max(0, int(round(x1 - pad_x))),
        max(0, int(round(y1 - pad_y))),
        min(image_w, int(round(x2 + pad_x))),
        min(image_h, int(round(y2 + pad_y))),
    ]


def format_seat_name(row: int, col: int) -> str:
    return f"第{row}排第{col}列"


def build_seats(detect_model: YOLO, cap, fps: float, duration_sec: float) -> list[dict]:
    print(
        f"[seat] start build seats: duration={duration_sec:.2f}s, sample_count={SEAT_FRAME_COUNT}, interval={SEAT_SEC}s",
        flush=True,
    )
    groups = []
    sec = 0.0
    used_count = 0

    while sec <= duration_sec and used_count < SEAT_FRAME_COUNT:
        ret, frame = read_frame_at(cap, fps, sec)
        if not ret or frame is None:
            break

        # 多帧采样
        result = detect_model.predict(
            source=frame,
            imgsz=IMG_SIZE,
            conf=DETECT_CONF,
            iou=DETECT_IOU,
            verbose=False,
        )[0]

        if result.boxes is not None:
            boxes = result.boxes.xyxy.tolist()
            confs = result.boxes.conf.tolist() if result.boxes.conf is not None else [0.0] * len(boxes)
            classes = result.boxes.cls.tolist() if result.boxes.cls is not None else [0] * len(boxes)

            for i, box in enumerate(boxes):
                cls_id = int(classes[i])
                if cls_id != 0:
                    continue
                score = float(confs[i])
                if score < DETECT_CONF:
                    continue

                found = None
                for group in groups:
                    if same_box(box, group["box"]):
                        found = group
                        break

                if found is None:
                    groups.append(
                        {
                            "box": box,
                            "boxes": [box],
                            "scores": [score],
                            "count": 1,
                        }
                    )
                else:
                    found["boxes"].append(box)
                    found["scores"].append(score)
                    found["count"] += 1
                    found["box"] = avg_box(found["boxes"])

        used_count += 1
        sec += SEAT_SEC

    before_filter = len(groups)
    # 过滤偶发框
    groups = [group for group in groups if group["count"] >= max(2, used_count // 3)]
    print(
        f"[seat] sampled_frames={used_count}, raw_groups={before_filter}, kept_groups={len(groups)}",
        flush=True,
    )
    groups.sort(key=lambda item: (item["box"][1], item["box"][0]))
    if not groups:
        print("[seat] no valid seat groups", flush=True)
        return []

    heights = [group["box"][3] - group["box"][1] for group in groups]
    row_gap = (sum(heights) / len(heights)) * 0.65 if heights else 80

    rows = []
    for group in groups:
        # 简单行聚类
        cy = (group["box"][1] + group["box"][3]) / 2.0
        joined = False
        for row in rows:
            if abs(cy - row["y"]) <= row_gap:
                row["items"].append(group)
                row["y"] = sum((item["box"][1] + item["box"][3]) / 2.0 for item in row["items"]) / len(row["items"])
                joined = True
                break
        if not joined:
            rows.append({"y": cy, "items": [group]})

    rows.sort(key=lambda row: row["y"])

    seats = []
    seat_id = 1
    for row_index, row in enumerate(rows, start=1):
        row["items"].sort(key=lambda item: item["box"][0])
        for col_index, group in enumerate(row["items"], start=1):
            seat_box = avg_box(group["boxes"])
            cx, cy = box_center(seat_box)
            seats.append(
                {
                    "seat_id": seat_id,
                    "seat_name": format_seat_name(row_index, col_index),
                    "row": row_index,
                    "col": col_index,
                    "box": seat_box,
                    "center": [round(cx, 2), round(cy, 2)],
                    "hit_count": group["count"],
                    "avg_conf": round(sum(group["scores"]) / len(group["scores"]), 4),
                }
            )
            seat_id += 1

    print(f"[seat] finished build seats: seat_count={len(seats)}", flush=True)
    return seats


def save_seat_map_image(frame, seats: list[dict], out_file: Path = SEAT_MAP_FILE) -> str:
    if frame is None:
        return ""

    image = frame.copy()
    for seat in seats:
        x1, y1, x2, y2 = [int(round(v)) for v in seat["box"]]
        cv2.rectangle(image, (x1, y1), (x2, y2), (18, 104, 243), 2)
        label = f"S{seat['seat_id']:02d}"
        label_y = max(22, y1 - 8)
        cv2.rectangle(image, (x1, label_y - 18), (x1 + 44, label_y + 4), (18, 104, 243), -1)
        cv2.putText(
            image,
            label,
            (x1 + 5, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_file), image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    rel_path = str(out_file.relative_to(ROOT_DIR)).replace("\\", "/")
    print(f"[seat] saved seat map: {rel_path}", flush=True)
    return rel_path


def save_raw_frame(frame, frame_index: int, sec: float, pose_utils: PoseDebugUtils) -> Path:
    file_name = f"frame_{frame_index:06d}_{pose_utils.format_time_file(sec)}_raw.jpg"
    file_path = RAW_DIR / file_name
    cv2.imwrite(str(file_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return file_path


def get_seat_color(status: str):
    if status == "STRONG":
        return 0, 0, 255
    if status == "WEAK":
        return 0, 255, 255
    if status == "NORMAL":
        return 0, 200, 0
    return 180, 180, 180


def pick_pose_result(result, crop_w: int, crop_h: int, seat_box_in_crop: list[float] | None = None):
    if result.boxes is None or result.keypoints is None:
        return None
    if len(result.boxes) == 0:
        return None

    crop_cx = crop_w / 2.0
    crop_cy = crop_h / 2.0
    best = None
    best_score = None

    boxes = result.boxes.xyxy
    confs = result.boxes.conf
    kpt_xy = result.keypoints.xy
    kpt_conf = result.keypoints.conf

    candidates = []
    for i in range(len(boxes)):
        box = boxes[i].tolist()
        cx, cy = box_center(box)
        dist = abs(cx - crop_cx) + abs(cy - crop_cy)
        score = float(confs[i].item()) if confs is not None else 0.0
        overlap = box_overlap_ratio(box, seat_box_in_crop) if seat_box_in_crop else 0.0
        rank = dist - score * 50 - overlap * 500
        candidates.append(
            {
                "rank": rank,
                "box": box,
                "conf": score,
                "seat_overlap": overlap,
                "kpt_xy": kpt_xy[i],
                "kpt_conf": kpt_conf[i],
            }
        )

    if seat_box_in_crop:
        candidates = [item for item in candidates if item["seat_overlap"] >= POSE_MIN_SEAT_OVERLAP]
        if not candidates:
            return None

    for item in candidates:
        if best is None or item["rank"] < best_score:
            best = item
            best_score = item["rank"]

    if best is not None:
        best.pop("rank", None)
    return best


def empty_seat_record(seat: dict, crop_box: list[int]) -> dict:
    return {
        "seat_id": seat["seat_id"],
        "seat_name": seat["seat_name"],
        "row": seat["row"],
        "col": seat["col"],
        "seat_box": seat["box"],
        "crop_box": crop_box,
        "status": "EMPTY",
        "ratio": None,
        "box_conf": None,
        "seat_overlap": None,
        "person_box": None,
        "valid": False,
        "reason": "no_person",
    }


def analyze_seat(pose_model, pose_utils: PoseDebugUtils, frame, seat: dict) -> dict:
    # 座位裁剪
    frame_h, frame_w = frame.shape[:2]
    cut_x1, cut_y1, cut_x2, cut_y2 = expand_box(seat["box"], frame_w, frame_h, SEAT_CROP_PAD)
    crop_box = [cut_x1, cut_y1, cut_x2, cut_y2]
    seat_item = empty_seat_record(seat, crop_box)
    crop = frame[cut_y1:cut_y2, cut_x1:cut_x2]
    if crop.size == 0:
        return seat_item

    seat_box_in_crop = [
        seat["box"][0] - cut_x1,
        seat["box"][1] - cut_y1,
        seat["box"][2] - cut_x1,
        seat["box"][3] - cut_y1,
    ]
    result = pose_model.predict(source=crop, imgsz=SEAT_IMG_SIZE, conf=POSE_CONF, iou=POSE_IOU, verbose=False)[0]
    picked = pick_pose_result(result, crop.shape[1], crop.shape[0], seat_box_in_crop)
    if picked is None:
        return seat_item

    # 姿态规则
    box = picked["box"]
    ratio_result = pose_utils.calc_head_shoulder_ratio(
        kpts_xy=picked["kpt_xy"],
        kpts_conf=picked["kpt_conf"],
        bbox_height=box[3] - box[1],
    )
    seat_item.update(
        {
            "status": pose_utils.classify_pose_by_ratio(ratio_result),
            "ratio": round(float(ratio_result.ratio), 4) if ratio_result.ratio is not None else None,
            "box_conf": round(float(picked["conf"]), 4),
            "seat_overlap": round(float(picked["seat_overlap"]), 4),
            "person_box": [
                round(box[0] + cut_x1, 2),
                round(box[1] + cut_y1, 2),
                round(box[2] + cut_x1, 2),
                round(box[3] + cut_y1, 2),
            ],
            "valid": ratio_result.valid,
            "reason": ratio_result.reason,
        }
    )
    return seat_item


def analyze_frame(pose_model, pose_utils: PoseDebugUtils, frame, frame_index: int, sec: float, seats: list[dict]):
    raw_file = save_raw_frame(frame, frame_index, sec, pose_utils)
    frame_h, frame_w = frame.shape[:2]
    frame_time = pose_utils.format_time_display(sec)
    record = {
        "frame_index": frame_index,
        "time": frame_time,
        "timestamp_seconds": round(float(sec), 3),
        "raw_frame": str(raw_file.relative_to(ROOT_DIR)).replace("\\", "/"),
        "frame_width": frame_w,
        "frame_height": frame_h,
        "seat_count": len(seats),
        "normal_count": 0,
        "weak_count": 0,
        "strong_count": 0,
        "empty_count": 0,
        "invalid_count": 0,
        "infer_seconds": 0,
        "seats": [],
    }

    start = time.time()
    for seat in seats:
        seat_item = analyze_seat(pose_model, pose_utils, frame, seat)
        key = f"{seat_item['status'].lower()}_count"
        if key in record:
            record[key] += 1
        record["seats"].append(seat_item)

    record["infer_seconds"] = round(time.time() - start, 3)
    print(
        "[frame] "
        f"index={frame_index}, time={frame_time}, normal={record['normal_count']}, "
        f"weak={record['weak_count']}, strong={record['strong_count']}, "
        f"empty={record['empty_count']}, invalid={record['invalid_count']}, "
        f"infer={record['infer_seconds']}s",
        flush=True,
    )
    return record


def start_event(event_id: int, frame_record: dict, seat: dict) -> dict:
    return {
        "event_id": event_id,
        "seat_id": seat["seat_id"],
        "seat_name": seat["seat_name"],
        "row": seat["row"],
        "col": seat["col"],
        "level": seat["status"],
        "start_time": frame_record["time"],
        "end_time": frame_record["time"],
        "start_timestamp_seconds": frame_record["timestamp_seconds"],
        "end_timestamp_seconds": frame_record["timestamp_seconds"],
        "peak_frame_index": frame_record["frame_index"],
        "peak_time": frame_record["time"],
        "peak_ratio": seat["ratio"],
        "peak_conf": seat["box_conf"],
        "seat_box": seat["seat_box"],
        "peak_person_box": seat["person_box"],
        "frames": [
            {
                "frame_index": frame_record["frame_index"],
                "time": frame_record["time"],
                "timestamp_seconds": frame_record["timestamp_seconds"],
                "raw_frame": frame_record["raw_frame"],
                "seat": seat,
            }
        ],
        "event_raw_image": "",
        "event_crops": [],
    }


def append_event(event: dict, frame_record: dict, seat: dict):
    event["frames"].append(
        {
            "frame_index": frame_record["frame_index"],
            "time": frame_record["time"],
            "timestamp_seconds": frame_record["timestamp_seconds"],
            "raw_frame": frame_record["raw_frame"],
            "seat": seat,
        }
    )
    event["end_time"] = frame_record["time"]
    event["end_timestamp_seconds"] = frame_record["timestamp_seconds"]
    old_ratio = event["peak_ratio"] if event["peak_ratio"] is not None else 999
    new_ratio = seat["ratio"] if seat["ratio"] is not None else 999
    if seat["status"] == "STRONG" and event["level"] != "STRONG":
        event["level"] = "STRONG"
        old_ratio = 999
    if new_ratio < old_ratio:
        event["peak_frame_index"] = frame_record["frame_index"]
        event["peak_time"] = frame_record["time"]
        event["peak_ratio"] = seat["ratio"]
        event["peak_conf"] = seat["box_conf"]
        event["peak_person_box"] = seat["person_box"]


def start_candidate_event(event_id: int, candidate_frames: list[dict]) -> dict:
    first = candidate_frames[0]
    event = start_event(event_id, first["frame"], first["seat"])
    for item in candidate_frames[1:]:
        append_event(event, item["frame"], item["seat"])
    return event


def build_events(frame_records: list[dict]) -> list[dict]:
    # 连续帧成事件
    states = {}
    events = []
    next_event_id = 1

    for frame_record in frame_records:
        for seat in frame_record["seats"]:
            seat_id = seat["seat_id"]
            state = states.setdefault(
                seat_id,
                {
                    "candidate": [],
                    "strong_streak": 0,
                    "abnormal_streak": 0,
                    "normal_streak": 0,
                    "active": None,
                },
            )

            is_abnormal = seat["status"] in {"WEAK", "STRONG"}
            if is_abnormal:
                state["normal_streak"] = 0
                state["abnormal_streak"] += 1
                state["strong_streak"] = state["strong_streak"] + 1 if seat["status"] == "STRONG" else 0

                if state["active"] is not None:
                    append_event(state["active"], frame_record, seat)
                    continue

                state["candidate"].append({"frame": frame_record, "seat": seat})
                should_start = (
                    state["strong_streak"] >= EVENT_START_STRONG_FRAMES
                    or state["abnormal_streak"] >= EVENT_START_WEAK_FRAMES
                )
                if should_start:
                    state["active"] = start_candidate_event(next_event_id, state["candidate"])
                    next_event_id += 1
                    state["candidate"] = []
            else:
                state["candidate"] = []
                state["strong_streak"] = 0
                state["abnormal_streak"] = 0
                if state["active"] is not None:
                    state["normal_streak"] += 1
                    if state["normal_streak"] >= EVENT_END_NORMAL_FRAMES:
                        events.append(state["active"])
                        state["active"] = None
                        state["normal_streak"] = 0

    for state in states.values():
        if state["active"] is not None:
            events.append(state["active"])

    for event in events:
        event["duration_seconds"] = round(
            event["end_timestamp_seconds"] - event["start_timestamp_seconds"],
            3,
        )
        event["frame_count"] = len(event["frames"])

    events.sort(key=lambda item: (item["row"], item["col"], item["start_timestamp_seconds"]))
    return events


def save_event_crop(raw_img, event: dict) -> dict | None:
    image_h, image_w = raw_img.shape[:2]
    seat_box = event["seat_box"]
    cut_x1, cut_y1, cut_x2, cut_y2 = expand_box(seat_box, image_w, image_h, 0.28)
    if cut_x2 <= cut_x1 or cut_y2 <= cut_y1:
        return None

    crop = raw_img[cut_y1:cut_y2, cut_x1:cut_x2].copy()
    sx1, sy1, sx2, sy2 = [int(round(v)) for v in seat_box]
    seat_layer = crop.copy()
    cv2.rectangle(seat_layer, (sx1 - cut_x1, sy1 - cut_y1), (sx2 - cut_x1, sy2 - cut_y1), (180, 150, 70), 1)
    crop = cv2.addWeighted(seat_layer, 0.35, crop, 0.65, 0)

    if event.get("peak_person_box"):
        px1, py1, px2, py2 = [int(round(v)) for v in event["peak_person_box"]]
        cv2.rectangle(crop, (px1 - cut_x1, py1 - cut_y1), (px2 - cut_x1, py2 - cut_y1), get_seat_color(event["level"]), 2)

    file_path = CROP_DIR / f"seat_{event['seat_id']:03d}_event_{event['event_id']:03d}.jpg"
    cv2.imwrite(str(file_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return {
        "seat_id": event["seat_id"],
        "seat_name": event["seat_name"],
        "status": event["level"],
        "ratio": event["peak_ratio"],
        "seat_box": seat_box,
        "image": str(file_path.relative_to(ROOT_DIR)).replace("\\", "/"),
    }


def save_event_assets(events: list[dict]):
    for event in events:
        peak_frame = None
        for frame in event["frames"]:
            if frame["frame_index"] == event["peak_frame_index"]:
                peak_frame = frame
                break
        if peak_frame is None:
            continue

        raw_file = ROOT_DIR / peak_frame["raw_frame"]
        event["event_raw_image"] = str(raw_file.relative_to(ROOT_DIR)).replace("\\", "/")
        raw_img = cv2.imread(str(raw_file))
        if raw_img is None:
            continue

        crop = save_event_crop(raw_img, event)
        event["event_crops"] = [crop] if crop else []


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    if not VIDEO_FILE.exists():
        print(f"视频不存在：{VIDEO_FILE}")
        return

    clear_out()
    detect_model = YOLO(str(DETECT_MODEL))
    pose_model = YOLO(str(POSE_MODEL))
    pose_utils = PoseDebugUtils(POSE_RULE)

    cap = cv2.VideoCapture(str(VIDEO_FILE))
    if not cap.isOpened():
        print(f"视频打开失败：{VIDEO_FILE}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps if fps and fps > 0 else 0

    seats = build_seats(detect_model, cap, fps, duration_sec)
    print(f"座位数：{len(seats)}")
    ret, seat_frame = read_frame_at(cap, fps, 0.0)
    seat_map_file = save_seat_map_image(seat_frame, seats) if ret else ""

    frame_records = []
    frame_index = 0
    sec = 0.0
    while sec <= duration_sec:
        ret, frame = read_frame_at(cap, fps, sec)
        if not ret or frame is None:
            break
        frame_index += 1
        frame_records.append(analyze_frame(pose_model, pose_utils, frame, frame_index, sec, seats))
        sec += FRAME_SEC

    cap.release()

    events = build_events(frame_records)
    save_event_assets(events)

    save_json(
        SEAT_JSON_FILE,
        {
            "video_path": str(VIDEO_REL_PATH).replace("\\", "/"),
            "seat_count": len(seats),
            "seat_map": seat_map_file,
            "seats": seats,
        },
    )
    save_json(
        FRAME_JSON_FILE,
        {
            "video_path": str(VIDEO_REL_PATH).replace("\\", "/"),
            "frame_interval_seconds": FRAME_SEC,
            "seat_count": len(seats),
            "frames": frame_records,
        },
    )
    save_json(
        EVENT_JSON_FILE,
        {
            "video_path": str(VIDEO_REL_PATH).replace("\\", "/"),
            "seat_count": len(seats),
            "seat_map": seat_map_file,
            "event_count": len(events),
            "events": events,
        },
    )

    print(f"座位结果：{SEAT_JSON_FILE}")
    print(f"帧结果：{FRAME_JSON_FILE}")
    print(f"事件结果：{EVENT_JSON_FILE}")


if __name__ == "__main__":
    main()
