import json
import shutil
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from pose_utils import PoseConfig, PoseDebugUtils

VIDEO_PATH = Path("inputs/video/test.mp4")

OUTPUT_DIR = Path("outputs/video_debug")
RAW_FRAME_OUTPUT_DIR = OUTPUT_DIR / "raw_frames"
DEBUG_FRAME_OUTPUT_DIR = OUTPUT_DIR / "frames"
EVENT_OUTPUT_DIR = OUTPUT_DIR / "events"
EVENT_CROP_OUTPUT_DIR = EVENT_OUTPUT_DIR / "crops"

FRAME_JSON_PATH = OUTPUT_DIR / "frame_result.json"
EVENT_JSON_PATH = OUTPUT_DIR / "event_result.json"

for path in [
    OUTPUT_DIR,
    RAW_FRAME_OUTPUT_DIR,
    DEBUG_FRAME_OUTPUT_DIR,
    EVENT_OUTPUT_DIR,
    EVENT_CROP_OUTPUT_DIR,
]:
    path.mkdir(parents=True, exist_ok=True)

MODEL_NAME = "yolo26s-pose.pt"

# YOLO 推理参数
IMG_SIZE = 3200
CONF = 0.15
IOU = 0.7

# 每隔几秒抽一帧
FRAME_INTERVAL_SECONDS = 5

# 连续两次异常帧最多允许隔多久，超过就当成新事件。
EVENT_GAP_SECONDS = FRAME_INTERVAL_SECONDS * 1.5

POSE_CONFIG = PoseConfig(
    keypoint_conf_threshold=0.3,
    strong_suspect_ratio=0.0,
    weak_suspect_ratio=0.10,
)


def ensure_output_dirs_clean():
    # demo 场景里，每次直接覆盖最新结果，比保留很多旧文件更省事。
    for path in [RAW_FRAME_OUTPUT_DIR, DEBUG_FRAME_OUTPUT_DIR, EVENT_OUTPUT_DIR]:
        if not path.exists():
            continue
        for child in path.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    EVENT_CROP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def status_score(status: str) -> int:
    if status == "STRONG":
        return 2
    if status == "WEAK":
        return 1
    return 0


def box_center(box: list[float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def box_iou(box1: list[float], box2: list[float]) -> float:
    inter_x1 = max(box1[0], box2[0])
    inter_y1 = max(box1[1], box2[1])
    inter_x2 = min(box1[2], box2[2])
    inter_y2 = min(box1[3], box2[3])

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union = area1 + area2 - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def is_same_person_box(box1: list[float], box2: list[float]) -> bool:
    if box_iou(box1, box2) >= 0.2:
        return True

    center1_x, center1_y = box_center(box1)
    center2_x, center2_y = box_center(box2)
    width_ref = max(40.0, min(box1[2] - box1[0], box2[2] - box2[0]))
    height_ref = max(60.0, min(box1[3] - box1[1], box2[3] - box2[1]))

    return (
        abs(center1_x - center2_x) <= width_ref * 0.6
        and abs(center1_y - center2_y) <= height_ref * 0.8
    )


def expand_box(box: list[float], image_width: int, image_height: int, scale: float = 0.8) -> list[int]:
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    pad_x = width * scale * 0.5
    pad_y = height * scale * 0.5

    ex1 = max(0, int(round(x1 - pad_x)))
    ey1 = max(0, int(round(y1 - pad_y)))
    ex2 = min(image_width, int(round(x2 + pad_x)))
    ey2 = min(image_height, int(round(y2 + pad_y)))
    return [ex1, ey1, ex2, ey2]


def save_focus_crop(raw_image, person: dict, event_id: int) -> dict | None:
    image_height, image_width = raw_image.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in person["bbox"]]
    crop_x1, crop_y1, crop_x2, crop_y2 = expand_box(person["bbox"], image_width, image_height)

    if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
        return None

    crop = raw_image[crop_y1:crop_y2, crop_x1:crop_x2].copy()
    cv2.rectangle(
        crop,
        (x1 - crop_x1, y1 - crop_y1),
        (x2 - crop_x1, y2 - crop_y1),
        (0, 255, 255) if person["status"] == "WEAK" else (0, 0, 255),
        2,
    )

    crop_path = EVENT_CROP_OUTPUT_DIR / (
        f"event_{event_id:03d}_peak_{person['status'].lower()}_focus.jpg"
    )
    cv2.imwrite(str(crop_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 100])

    return {
        "person_id": person["id"],
        "status": person["status"],
        "ratio": person["ratio"],
        "bbox": person["bbox"],
        "focus_bbox": [crop_x1, crop_y1, crop_x2, crop_y2],
        "image": str(crop_path).replace("\\", "/"),
    }


def save_raw_frame(frame, frame_index: int, timestamp_seconds: float, pose_utils: PoseDebugUtils) -> Path:
    frame_time_name = pose_utils.format_time_file(timestamp_seconds)
    output_path = RAW_FRAME_OUTPUT_DIR / f"frame_{frame_index:06d}_{frame_time_name}_raw.png"
    cv2.imwrite(str(output_path), frame)
    return output_path


def save_debug_frame(debug_image, frame_index: int, timestamp_seconds: float, pose_utils: PoseDebugUtils) -> Path:
    frame_time_name = pose_utils.format_time_file(timestamp_seconds)
    output_path = DEBUG_FRAME_OUTPUT_DIR / f"frame_{frame_index:06d}_{frame_time_name}_debug.jpg"
    cv2.imwrite(str(output_path), debug_image, [cv2.IMWRITE_JPEG_QUALITY, 100])
    return output_path


def build_person_record(person_index: int, box, box_conf: float, pose_status: str, ratio_result) -> dict:
    return {
        "id": person_index,
        "bbox": [round(float(v), 2) for v in box],
        "box_conf": round(float(box_conf), 4),
        "status": pose_status,
        "score": status_score(pose_status),
        "ratio": round(float(ratio_result.ratio), 4) if ratio_result.ratio is not None else None,
        "valid": ratio_result.valid,
        "invalid_reason": None if ratio_result.valid else ratio_result.reason,
    }


def analyze_frame(
    model,
    pose_utils: PoseDebugUtils,
    frame,
    frame_index: int,
    timestamp_seconds: float,
):
    frame_time_display = pose_utils.format_time_display(timestamp_seconds)
    raw_frame_path = save_raw_frame(frame, frame_index, timestamp_seconds, pose_utils)

    height, width = frame.shape[:2]
    frame_record = {
        "frame_index": frame_index,
        "time": frame_time_display,
        "timestamp_seconds": round(float(timestamp_seconds), 3),
        "raw_frame": str(raw_frame_path).replace("\\", "/"),
        "debug_image": "",
        "frame_width": int(width),
        "frame_height": int(height),
        "person_count": 0,
        "normal_count": 0,
        "weak_count": 0,
        "strong_count": 0,
        "invalid_count": 0,
        "suspicious_count": 0,
        "frame_score": 0,
        "infer_seconds": 0,
        "persons": [],
    }

    start_time = time.time()
    result = model.predict(
        source=frame,
        imgsz=IMG_SIZE,
        conf=CONF,
        iou=IOU,
        verbose=False,
    )[0]
    frame_record["infer_seconds"] = round(time.time() - start_time, 3)

    debug_image = frame.copy()
    if result.boxes is None or result.keypoints is None:
        debug_output_path = save_debug_frame(debug_image, frame_index, timestamp_seconds, pose_utils)
        frame_record["debug_image"] = str(debug_output_path).replace("\\", "/")
        return frame_record

    boxes = result.boxes.xyxy
    box_confs = result.boxes.conf
    keypoints_xy = result.keypoints.xy
    keypoints_conf = result.keypoints.conf

    frame_record["person_count"] = len(boxes)

    for i in range(len(boxes)):
        box = boxes[i].tolist()
        x1, y1, x2, y2 = box
        bbox_height = y2 - y1

        ratio_result = pose_utils.calc_head_shoulder_ratio(
            kpts_xy=keypoints_xy[i],
            kpts_conf=keypoints_conf[i],
            bbox_height=bbox_height,
        )
        pose_status = pose_utils.classify_pose_by_ratio(ratio_result)

        if pose_status == "NORMAL":
            frame_record["normal_count"] += 1
        elif pose_status == "WEAK":
            frame_record["weak_count"] += 1
        elif pose_status == "STRONG":
            frame_record["strong_count"] += 1
        else:
            frame_record["invalid_count"] += 1

        frame_record["frame_score"] += status_score(pose_status)
        if pose_status in {"WEAK", "STRONG"}:
            frame_record["suspicious_count"] += 1

        x1_i, y1_i, x2_i, y2_i = map(int, [x1, y1, x2, y2])
        cv2.rectangle(
            debug_image,
            (x1_i, y1_i),
            (x2_i, y2_i),
            pose_utils.get_box_color(pose_status),
            2,
        )

        if ratio_result.valid:
            label = f"ID:{i + 1} {pose_status} r:{ratio_result.ratio:.3f}"
        else:
            label = f"ID:{i + 1} INVALID {ratio_result.reason}"

        pose_utils.put_label(debug_image, label, max(0, x1_i), max(25, y1_i - 8))
        frame_record["persons"].append(
            build_person_record(i + 1, box, box_confs[i], pose_status, ratio_result)
        )

    debug_output_path = save_debug_frame(debug_image, frame_index, timestamp_seconds, pose_utils)
    frame_record["debug_image"] = str(debug_output_path).replace("\\", "/")
    return frame_record


def read_frame_at_second(cap, fps: float, timestamp_seconds: float):
    if fps <= 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000)
    else:
        target_frame_index = int(round(timestamp_seconds * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_index)

    ret, frame = cap.read()
    return ret, frame


def start_event(event_id: int, frame_record: dict, person: dict) -> dict:
    return {
        "event_id": event_id,
        "type": "sleep_pose",
        "level": person["status"],
        "start_time": frame_record["time"],
        "end_time": frame_record["time"],
        "start_timestamp_seconds": frame_record["timestamp_seconds"],
        "end_timestamp_seconds": frame_record["timestamp_seconds"],
        "peak_frame_index": frame_record["frame_index"],
        "peak_time": frame_record["time"],
        "peak_timestamp_seconds": frame_record["timestamp_seconds"],
        "peak_score": person["score"],
        "peak_person_id": person["id"],
        "peak_ratio": person["ratio"],
        "peak_bbox": person["bbox"],
        "last_bbox": person["bbox"],
        "frames": [
            {
                "frame_index": frame_record["frame_index"],
                "time": frame_record["time"],
                "timestamp_seconds": frame_record["timestamp_seconds"],
                "debug_image": frame_record["debug_image"],
                "raw_frame": frame_record["raw_frame"],
                "person": person,
            }
        ],
        "event_debug_image": "",
        "event_raw_image": "",
        "event_crops": [],
    }


def append_event_frame(event: dict, frame_record: dict, person: dict):
    event["frames"].append(
        {
            "frame_index": frame_record["frame_index"],
            "time": frame_record["time"],
            "timestamp_seconds": frame_record["timestamp_seconds"],
            "debug_image": frame_record["debug_image"],
            "raw_frame": frame_record["raw_frame"],
            "person": person,
        }
    )
    event["end_time"] = frame_record["time"]
    event["end_timestamp_seconds"] = frame_record["timestamp_seconds"]
    event["last_bbox"] = person["bbox"]

    if person["status"] == "STRONG":
        event["level"] = "STRONG"

    if person["score"] > event["peak_score"]:
        event["peak_score"] = person["score"]
        event["peak_frame_index"] = frame_record["frame_index"]
        event["peak_time"] = frame_record["time"]
        event["peak_timestamp_seconds"] = frame_record["timestamp_seconds"]
        event["peak_person_id"] = person["id"]
        event["peak_ratio"] = person["ratio"]
        event["peak_bbox"] = person["bbox"]
    elif person["score"] == event["peak_score"]:
        current_ratio = person["ratio"] if person["ratio"] is not None else 999
        peak_ratio = event["peak_ratio"] if event["peak_ratio"] is not None else 999
        if current_ratio < peak_ratio:
            event["peak_frame_index"] = frame_record["frame_index"]
            event["peak_time"] = frame_record["time"]
            event["peak_timestamp_seconds"] = frame_record["timestamp_seconds"]
            event["peak_person_id"] = person["id"]
            event["peak_ratio"] = person["ratio"]
            event["peak_bbox"] = person["bbox"]


def finalize_event(event: dict):
    event["duration_seconds"] = round(
        event["end_timestamp_seconds"] - event["start_timestamp_seconds"],
        3,
    )
    event["frame_count"] = len(event["frames"])
    event["summary"] = (
        f"{event['type']} {event['level']}, "
        f"{event['start_time']} ~ {event['end_time']}, "
        f"峰值比例 {event['peak_ratio']}"
    )
    del event["last_bbox"]


def keep_event(event: dict) -> bool:
    # 这里只做很轻的过滤：
    # 强异常允许更敏感一些，弱异常要求至少持续两三次抽帧，避免单帧噪声太多。
    peak_ratio = event["peak_ratio"] if event["peak_ratio"] is not None else 999

    if event["level"] == "STRONG":
        return event["frame_count"] >= 2 or peak_ratio <= -0.02

    if event["frame_count"] >= 3:
        return True

    return event["frame_count"] >= 2 and peak_ratio <= 0.04


def build_events(frame_records: list[dict]) -> list[dict]:
    events = []
    active_events = []
    next_event_id = 1

    for frame_record in frame_records:
        suspicious_persons = [
            person
            for person in frame_record["persons"]
            if person["status"] in {"WEAK", "STRONG"}
        ]
        suspicious_persons.sort(
            key=lambda person: (-person["score"], person["ratio"] if person["ratio"] is not None else 999)
        )

        still_active = []
        for event in active_events:
            gap_seconds = frame_record["timestamp_seconds"] - event["end_timestamp_seconds"]
            if gap_seconds > EVENT_GAP_SECONDS:
                finalize_event(event)
                events.append(event)
            else:
                still_active.append(event)
        active_events = still_active

        matched_event_ids = set()
        for person in suspicious_persons:
            matched_event = None
            best_iou = -1.0

            for event in active_events:
                if event["event_id"] in matched_event_ids:
                    continue
                if not is_same_person_box(person["bbox"], event["last_bbox"]):
                    continue

                overlap = box_iou(person["bbox"], event["last_bbox"])
                if overlap > best_iou:
                    best_iou = overlap
                    matched_event = event

            if matched_event is None:
                new_event = start_event(next_event_id, frame_record, person)
                active_events.append(new_event)
                matched_event_ids.add(new_event["event_id"])
                next_event_id += 1
                continue

            append_event_frame(matched_event, frame_record, person)
            matched_event_ids.add(matched_event["event_id"])

    for event in active_events:
        finalize_event(event)
        events.append(event)

    return sorted(
        [event for event in events if keep_event(event)],
        key=lambda event: (event["start_timestamp_seconds"], event["event_id"]),
    )


def save_event_assets(events: list[dict]):
    for event in events:
        peak_frame = None
        for frame in event["frames"]:
            if frame["frame_index"] == event["peak_frame_index"]:
                peak_frame = frame
                break

        if peak_frame is None:
            continue

        debug_src = Path(peak_frame["debug_image"])
        raw_src = Path(peak_frame["raw_frame"])
        debug_dst = EVENT_OUTPUT_DIR / f"event_{event['event_id']:03d}_debug.jpg"
        raw_dst = EVENT_OUTPUT_DIR / f"event_{event['event_id']:03d}_raw.png"

        shutil.copy2(debug_src, debug_dst)
        shutil.copy2(raw_src, raw_dst)

        event["event_debug_image"] = str(debug_dst).replace("\\", "/")
        event["event_raw_image"] = str(raw_dst).replace("\\", "/")

        raw_image = cv2.imread(str(raw_src))
        if raw_image is None:
            continue

        peak_person = peak_frame["person"]
        focus_crop = save_focus_crop(raw_image, peak_person, event["event_id"])
        event["event_crops"] = [focus_crop] if focus_crop is not None else []


def main():
    if not VIDEO_PATH.exists():
        print(f"视频不存在：{VIDEO_PATH}")
        return

    ensure_output_dirs_clean()

    print(f"加载模型：{MODEL_NAME}")
    model = YOLO(MODEL_NAME)
    pose_utils = PoseDebugUtils(POSE_CONFIG)

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        print(f"视频打开失败：{VIDEO_PATH}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_seconds = total_frames / fps if fps and fps > 0 else 0

    ret, first_frame = read_frame_at_second(cap, fps, 0)
    if not ret:
        print("无法读取视频第一帧")
        cap.release()
        return

    first_height, first_width = first_frame.shape[:2]

    print(f"视频路径：{VIDEO_PATH}")
    print(f"FPS：{fps}")
    print(f"总帧数：{total_frames}")
    print(f"视频时长：{pose_utils.format_time_display(duration_seconds)}")
    print(f"视频原始解码帧尺寸：width={first_width}, height={first_height}")
    print(f"抽帧间隔：{FRAME_INTERVAL_SECONDS} 秒")
    print(f"模型参数：imgsz={IMG_SIZE}, conf={CONF}, iou={IOU}")

    frame_records = []
    frame_index = 0
    timestamp_seconds = 0.0

    while timestamp_seconds <= duration_seconds:
        ret, frame = read_frame_at_second(cap, fps, timestamp_seconds)
        if not ret:
            break

        frame_index += 1
        print(
            f"\n正在分析第 {frame_index} 帧，"
            f"时间：{pose_utils.format_time_display(timestamp_seconds)}"
        )

        frame_record = analyze_frame(
            model=model,
            pose_utils=pose_utils,
            frame=frame,
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
        )
        frame_records.append(frame_record)

        print(
            f"检测人数={frame_record['person_count']}, "
            f"NORMAL={frame_record['normal_count']}, "
            f"WEAK={frame_record['weak_count']}, "
            f"STRONG={frame_record['strong_count']}, "
            f"异常人数={frame_record['suspicious_count']}, "
            f"耗时={frame_record['infer_seconds']}秒"
        )

        timestamp_seconds += FRAME_INTERVAL_SECONDS

    cap.release()

    events = build_events(frame_records)
    save_event_assets(events)

    frame_results = {
        "video_path": str(VIDEO_PATH).replace("\\", "/"),
        "model_name": MODEL_NAME,
        "imgsz": IMG_SIZE,
        "conf": CONF,
        "iou": IOU,
        "frame_interval_seconds": FRAME_INTERVAL_SECONDS,
        "fps": fps,
        "total_frames": total_frames,
        "duration_seconds": round(float(duration_seconds), 3),
        "video_width": int(first_width),
        "video_height": int(first_height),
        "frames": frame_records,
    }

    event_results = {
        "video_path": str(VIDEO_PATH).replace("\\", "/"),
        "frame_interval_seconds": FRAME_INTERVAL_SECONDS,
        "event_gap_seconds": EVENT_GAP_SECONDS,
        "event_count": len(events),
        "events": events,
    }

    with open(FRAME_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(frame_results, f, ensure_ascii=False, indent=2)

    with open(EVENT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(event_results, f, ensure_ascii=False, indent=2)

    print("\n视频异常事件分析完成")
    print(f"原始抽帧目录：{RAW_FRAME_OUTPUT_DIR}")
    print(f"调试帧目录：{DEBUG_FRAME_OUTPUT_DIR}")
    print(f"事件截图目录：{EVENT_OUTPUT_DIR}")
    print(f"逐帧 JSON：{FRAME_JSON_PATH}")
    print(f"事件 JSON：{EVENT_JSON_PATH}")
    print(f"异常事件数：{len(events)}")


if __name__ == "__main__":
    main()
