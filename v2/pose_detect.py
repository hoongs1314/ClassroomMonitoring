import argparse
import json
import shutil
from pathlib import Path

import cv2
from ultralytics import YOLO


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SEAT_DIR = ROOT_DIR / "outputs" / "v2" / "seats_sahi_v3"
DEFAULT_MODEL = ROOT_DIR / "models" / "yolo26s-pose.pt"
DEFAULT_OUTPUT = ROOT_DIR / "outputs" / "v2" / "pose"

HEAD_IDS = [0, 1, 2, 3, 4]
SHOULDER_IDS = [5, 6]
KEYPOINT_NAMES = {
    0: "nose",
    1: "left_eye",
    2: "right_eye",
    3: "left_ear",
    4: "right_ear",
    5: "left_shoulder",
    6: "right_shoulder",
}


def box_center(box):
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def box_overlap_ratio(box1, box2) -> float:
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    small_area = min(area1, area2)
    return inter / small_area if small_area > 0 else 0.0


def normalized_center_distance(box, anchor_box) -> float:
    cx, cy = box_center(box)
    ax, ay = box_center(anchor_box)
    aw = max(1.0, anchor_box[2] - anchor_box[0])
    ah = max(1.0, anchor_box[3] - anchor_box[1])
    return (((cx - ax) / aw) ** 2 + ((cy - ay) / ah) ** 2) ** 0.5


def visible_point(kpt_xy, kpt_conf, index: int, threshold: float):
    conf = float(kpt_conf[index])
    if conf < threshold:
        return None
    return {
        "id": index,
        "name": KEYPOINT_NAMES.get(index, str(index)),
        "x": float(kpt_xy[index][0]),
        "y": float(kpt_xy[index][1]),
        "conf": conf,
    }


def average_point(points):
    return {
        "x": sum(item["x"] for item in points) / len(points),
        "y": sum(item["y"] for item in points) / len(points),
        "conf": sum(item["conf"] for item in points) / len(points),
    }


def classify_head_shoulder(kpt_xy, kpt_conf, bbox, args):
    head_points = [visible_point(kpt_xy, kpt_conf, idx, args.kpt_conf) for idx in HEAD_IDS]
    shoulder_points = [visible_point(kpt_xy, kpt_conf, idx, args.kpt_conf) for idx in SHOULDER_IDS]
    head_points = [item for item in head_points if item is not None]
    shoulder_points = [item for item in shoulder_points if item is not None]

    if len(shoulder_points) < 2:
        return {
            "status": "INVALID",
            "ratio": None,
            "reason": "shoulder_low",
            "head_points": head_points,
            "shoulder_points": shoulder_points,
        }

    if not head_points:
        return {
            "status": "STRONG",
            "ratio": None,
            "reason": "head_missing",
            "head_points": head_points,
            "shoulder_points": shoulder_points,
        }

    head_center = average_point(head_points)
    shoulder_center = average_point(shoulder_points)
    bbox_h = max(1.0, bbox[3] - bbox[1])
    ratio = (shoulder_center["y"] - head_center["y"]) / bbox_h

    if ratio < args.strong_ratio:
        status = "STRONG"
    elif ratio < args.weak_ratio:
        status = "WEAK"
    else:
        status = "NORMAL"

    return {
        "status": status,
        "ratio": round(float(ratio), 4),
        "reason": "ok",
        "head_center": {
            "x": round(head_center["x"], 2),
            "y": round(head_center["y"], 2),
            "conf": round(head_center["conf"], 4),
        },
        "shoulder_center": {
            "x": round(shoulder_center["x"], 2),
            "y": round(shoulder_center["y"], 2),
            "conf": round(shoulder_center["conf"], 4),
        },
        "head_points": head_points,
        "shoulder_points": shoulder_points,
    }


def pick_pose(result, seat_box_in_crop, args):
    if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
        return None

    boxes = result.boxes.xyxy
    confs = result.boxes.conf
    kpt_xy = result.keypoints.xy
    kpt_conf = result.keypoints.conf

    candidates = []
    for index in range(len(boxes)):
        box = boxes[index].tolist()
        score = float(confs[index].item()) if confs is not None else 0.0
        overlap = box_overlap_ratio(box, seat_box_in_crop) if seat_box_in_crop else 0.0
        distance = normalized_center_distance(box, seat_box_in_crop) if seat_box_in_crop else 0.0
        area = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
        rank = overlap * 300 + score * 100 - distance * 80 + area / 20000
        candidates.append(
            {
                "rank": rank,
                "box": box,
                "conf": score,
                "seat_overlap": overlap,
                "seat_center_distance": distance,
                "kpt_xy": kpt_xy[index],
                "kpt_conf": kpt_conf[index],
            }
        )

    if seat_box_in_crop:
        overlapping = [item for item in candidates if item["seat_overlap"] >= args.min_overlap]
        if overlapping:
            candidates = overlapping

    picked = max(candidates, key=lambda item: item["rank"])
    picked["candidate_count"] = len(candidates)
    return picked


def draw_result(image, picked, classify, output_file: Path):
    canvas = image.copy()
    color_map = {
        "STRONG": (0, 0, 255),
        "WEAK": (0, 255, 255),
        "NORMAL": (0, 200, 0),
        "INVALID": (160, 160, 160),
        "EMPTY": (160, 160, 160),
    }
    color = color_map.get(classify["status"], (255, 255, 255))

    if picked is not None:
        x1, y1, x2, y2 = [int(round(v)) for v in picked["box"]]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        for point in classify.get("head_points", []) + classify.get("shoulder_points", []):
            cv2.circle(canvas, (int(round(point["x"])), int(round(point["y"]))), 4, color, -1)

        if "head_center" in classify:
            hc = classify["head_center"]
            sc = classify["shoulder_center"]
            cv2.line(
                canvas,
                (int(round(hc["x"])), int(round(hc["y"]))),
                (int(round(sc["x"])), int(round(sc["y"]))),
                color,
                2,
            )

    label = f"{classify['status']} {classify.get('ratio', '')} {classify['reason']}"
    cv2.rectangle(canvas, (0, 0), (min(canvas.shape[1], 360), 30), color, -1)
    cv2.putText(canvas, label, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_file), canvas, [cv2.IMWRITE_JPEG_QUALITY, 95])


def parse_args():
    parser = argparse.ArgumentParser(description="V2 pose detector: run pose on seat crop images.")
    parser.add_argument("--seat-dir", type=Path, default=DEFAULT_SEAT_DIR)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--iou", type=float, default=0.6)
    parser.add_argument("--kpt-conf", type=float, default=0.20)
    parser.add_argument(
        "--min-overlap",
        type=float,
        default=0.0,
        help="Minimum overlap with original seat box before filtering candidates. Default keeps recall first.",
    )
    parser.add_argument("--strong-ratio", type=float, default=-0.10)
    parser.add_argument("--weak-ratio", type=float, default=0.03)
    parser.add_argument("--clean", action="store_true", help="Remove old output before running pose detection.")
    return parser.parse_args()


def main():
    args = parse_args()
    seat_dir = args.seat_dir if args.seat_dir.is_absolute() else ROOT_DIR / args.seat_dir
    model_file = args.model if args.model.is_absolute() else ROOT_DIR / args.model
    output_dir = args.output if args.output.is_absolute() else ROOT_DIR / args.output

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(seat_dir / "seats.json", "r", encoding="utf-8") as f:
        seat_data = json.load(f)

    seat_map = {item["seat_id"]: item for item in seat_data["seats"]}
    model = YOLO(str(model_file))
    results = []

    for crop_record in seat_data["crops"]:
        image_file = seat_dir / crop_record["image"]
        image = cv2.imread(str(image_file))
        if image is None:
            continue

        result = model.predict(
            source=image,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            verbose=False,
        )[0]
        picked = pick_pose(result, crop_record.get("seat_box_in_crop"), args)

        if picked is None:
            classify = {
                "status": "EMPTY",
                "ratio": None,
                "reason": "no_pose_person",
                "head_points": [],
                "shoulder_points": [],
            }
            person_box = None
            person_conf = None
            seat_overlap = None
            seat_center_distance = None
            candidate_count = 0
        else:
            classify = classify_head_shoulder(picked["kpt_xy"], picked["kpt_conf"], picked["box"], args)
            person_box = [round(float(value), 2) for value in picked["box"]]
            person_conf = round(float(picked["conf"]), 4)
            seat_overlap = round(float(picked["seat_overlap"]), 4)
            seat_center_distance = round(float(picked["seat_center_distance"]), 4)
            candidate_count = int(picked["candidate_count"])

        seat = seat_map[crop_record["seat_id"]]
        annotated_file = (
            output_dir
            / "annotated"
            / crop_record["seat_code"]
            / Path(crop_record["image"]).name
        )
        draw_result(image, picked, classify, annotated_file)

        results.append(
            {
                "seat_id": crop_record["seat_id"],
                "seat_code": crop_record["seat_code"],
                "seat_name": seat["seat_name"],
                "time": crop_record["time"],
                "time_seconds": crop_record["time_seconds"],
                "source_image": crop_record["image"],
                "annotated_image": str(annotated_file.relative_to(output_dir)).replace("\\", "/"),
                "status": classify["status"],
                "ratio": classify.get("ratio"),
                "reason": classify["reason"],
                "person_box": person_box,
                "person_conf": person_conf,
                "seat_overlap": seat_overlap,
                "seat_center_distance": seat_center_distance,
                "candidate_count": candidate_count,
                "head_points": classify.get("head_points", []),
                "shoulder_points": classify.get("shoulder_points", []),
                "head_center": classify.get("head_center"),
                "shoulder_center": classify.get("shoulder_center"),
            }
        )

    summary = {}
    for item in results:
        seat_summary = summary.setdefault(
            item["seat_code"],
            {
                "seat_id": item["seat_id"],
                "seat_code": item["seat_code"],
                "seat_name": item["seat_name"],
                "total": 0,
                "status_counts": {},
            },
        )
        seat_summary["total"] += 1
        seat_summary["status_counts"][item["status"]] = seat_summary["status_counts"].get(item["status"], 0) + 1

    output = {
        "seat_dir": str(seat_dir.relative_to(ROOT_DIR)).replace("\\", "/") if seat_dir.is_relative_to(ROOT_DIR) else str(seat_dir),
        "model": str(model_file.relative_to(ROOT_DIR)).replace("\\", "/") if model_file.is_relative_to(ROOT_DIR) else str(model_file),
        "image_count": len(results),
        "summary": list(summary.values()),
        "results": results,
    }
    with open(output_dir / "pose_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"image_count={len(results)}")
    print(f"output={output_dir}")


if __name__ == "__main__":
    main()
