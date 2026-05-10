import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SEAT_DIR = ROOT_DIR / "outputs" / "v2" / "seats_sahi_v3"
DEFAULT_MODEL = ROOT_DIR / "models" / "yolo26s-pose.pt" # 建议确认模型是否存在
DEFAULT_OUTPUT = ROOT_DIR / "outputs" / "v2" / "pose_v3"

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
    # 归一化欧氏距离
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
    if not points:
        return None
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


def pick_pose(result, seat_box_in_crop, image_shape, args):
    if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
        return None

    img_h, img_w = image_shape[:2]
    crop_center_box = [0, 0, img_w, img_h] # 裁剪图的全图作为参考

    boxes = result.boxes.xyxy
    confs = result.boxes.conf
    kpt_xy = result.keypoints.xy
    kpt_conf = result.keypoints.conf

    candidates = []
    for index in range(len(boxes)):
        box = boxes[index].tolist()
        score = float(confs[index].item()) if confs is not None else 0.0
        
        # 计算与原始座位框的重叠度
        overlap = box_overlap_ratio(box, seat_box_in_crop) if seat_box_in_crop else 0.5
        # 计算与裁剪图中心的距离（归一化）
        dist_to_center = normalized_center_distance(box, crop_center_box)
        
        # 关键点质量评估：计算鼻部和肩部的平均置信度
        kpts_c = kpt_conf[index]
        kpts_xy = kpt_xy[index]
        main_kpts_conf = np.mean([kpts_c[i].item() for i in (HEAD_IDS + SHOULDER_IDS)])
        
        # 面积占比（目标人物应该占据裁剪图的一大部分）
        area_ratio = (max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])) / (img_w * img_h)
        
        # 综合评分算法（V3 增强版）
        # 1. 重叠度权重最高 (400)
        # 2. 中心距离惩罚极大 (-250)
        # 3. 关键点质量权重 (150)
        # 4. 面积合理性：倾向于占据 30%-80% 面积的人
        area_score = 1.0 - abs(area_ratio - 0.5) * 2 
        
        rank = (overlap * 400) + (main_kpts_conf * 150) + (score * 100) - (dist_to_center * 250) + (area_score * 50)
        
        candidates.append(
            {
                "rank": rank,
                "box": box,
                "conf": score,
                "seat_overlap": overlap,
                "dist_to_center": dist_to_center,
                "kpt_xy": kpts_xy.cpu().numpy(),
                "kpt_conf": kpts_c.cpu().numpy(),
                "area_ratio": area_ratio
            }
        )

    # 过滤：必须有一定的重叠度，且不能离中心太远
    filtered = [c for c in candidates if c["seat_overlap"] >= 0.2 and c["dist_to_center"] <= 0.8]
    if not filtered:
        # 如果过滤后没了，回退到原始 candidates 但降低 rank
        filtered = candidates

    picked = max(filtered, key=lambda item: item["rank"])
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
        # 绘制所有关键点
        for i in range(len(picked["kpt_xy"])):
            pt = picked["kpt_xy"][i]
            conf = picked["kpt_conf"][i]
            if conf > 0.3:
                cv2.circle(canvas, (int(round(float(pt[0]))), int(round(float(pt[1])))), 3, (255, 0, 0), -1)

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
    cv2.rectangle(canvas, (0, 0), (min(canvas.shape[1], 400), 30), color, -1)
    cv2.putText(canvas, label, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_file), canvas, [cv2.IMWRITE_JPEG_QUALITY, 95])


def parse_args():
    parser = argparse.ArgumentParser(description="V3 pose detector: optimized for seat crops with center-locking.")
    parser.add_argument("--seat-dir", type=Path, default=DEFAULT_SEAT_DIR)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--imgsz", type=int, default=640, help="对于小图裁剪，640 通常比 960 更稳定。")
    parser.add_argument("--conf", type=float, default=0.25, help="提高置信度阈值。")
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--kpt-conf", type=float, default=0.30, help="提高关键点置信度阈值。")
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

    seats_json_path = seat_dir / "seats.json"
    if not seats_json_path.exists():
        print(f"Error: {seats_json_path} not found. Please run seat_detect_sahi_v3.py first.")
        return

    with open(seats_json_path, "r", encoding="utf-8") as f:
        seat_data = json.load(f)

    seat_map = {item["seat_id"]: item for item in seat_data["seats"]}
    model = YOLO(str(model_file))
    results = []
    total_crops = len(seat_data["crops"])

    print(f"Starting pose detection on {total_crops} images...")

    for i, crop_record in enumerate(seat_data["crops"]):
        # 每处理 5% 或 10 张图打印一次进度
        if i % max(1, total_crops // 20) == 0 or i < 5:
            print(f"  Progress: {i}/{total_crops} ({i/total_crops*100:.1f}%)")

        image_file = seat_dir / crop_record["image"]
        image = cv2.imread(str(image_file))
        if image is None:
            continue

        # 核心修复：处理 v3 版本的键名 original_seat_box_in_crop
        seat_box_in_crop = crop_record.get("original_seat_box_in_crop") or crop_record.get("seat_box_in_crop")

        result = model.predict(
            source=image,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            half=False, # CPU 环境下建议关闭 half
            verbose=False,
        )[0]
        
        picked = pick_pose(result, seat_box_in_crop, image.shape, args)

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
            dist_to_center = None
            candidate_count = 0
        else:
            classify = classify_head_shoulder(picked["kpt_xy"], picked["kpt_conf"], picked["box"], args)
            person_box = [round(float(value), 2) for value in picked["box"]]
            person_conf = round(float(picked["conf"]), 4)
            seat_overlap = round(float(picked["seat_overlap"]), 4)
            dist_to_center = round(float(picked["dist_to_center"]), 4)
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
                "dist_to_center": dist_to_center,
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
