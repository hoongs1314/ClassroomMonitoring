import argparse
import json
import shutil
from pathlib import Path

import cv2
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction


ROOT_DIR = Path(__file__).resolve().parents[1]
VIDEO_FILE = ROOT_DIR / "inputs/video/test.mp4"
MODEL_FILE = ROOT_DIR / "models/detect.pt"
OUTPUT_DIR = ROOT_DIR / "outputs/v2/seats_sahi_v3"
PERSON_CLASS = 0
DEVICE = "cpu"


def read_frame_at(cap, fps: float, sec: float):
    """读取视频中指定秒数附近的一帧。"""
    if fps <= 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
    else:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(sec * fps)))
    return cap.read()


def box_center(box):
    """计算 xyxy 框的中心点坐标。"""
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def box_overlap_ratio(box1, box2) -> float:
    """计算两个框相对较小框面积的重叠比例。"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    small_area = min(area1, area2)
    return inter / small_area if small_area > 0 else 0.0


def box_iou(box1, box2) -> float:
    """计算两个框的 IoU，用于判断是否为同一个人。"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def same_box(box1, box2) -> bool:
    """判断两个检测框是否属于同一个人，避免把相邻人员合并到中间。"""
    x1, y1 = box_center(box1)
    x2, y2 = box_center(box2)
    w = max(40.0, min(box1[2] - box1[0], box2[2] - box2[0]))
    h = max(60.0, min(box1[3] - box1[1], box2[3] - box2[1]))
    center_close = abs(x1 - x2) <= w * 0.45 and abs(y1 - y2) <= h * 0.55
    return center_close and (box_iou(box1, box2) >= 0.20 or box_overlap_ratio(box1, box2) >= 0.55)


def avg_box(box_list):
    """对同一座位的多个检测框求平均框。"""
    size = len(box_list)
    return [
        round(sum(box[0] for box in box_list) / size, 2),
        round(sum(box[1] for box in box_list) / size, 2),
        round(sum(box[2] for box in box_list) / size, 2),
        round(sum(box[3] for box in box_list) / size, 2),
    ]


def union_box(box_list):
    """把同组检测框合并为覆盖所有命中位置的外接框。"""
    return [
        round(min(box[0] for box in box_list), 2),
        round(min(box[1] for box in box_list), 2),
        round(max(box[2] for box in box_list), 2),
        round(max(box[3] for box in box_list), 2),
    ]


def best_box(box_list, scores):
    """选取同组中置信度最高的框作为座位锚点。"""
    best_index = max(range(len(box_list)), key=lambda index: scores[index])
    return [round(value, 2) for value in box_list[best_index]]


def normalize_anchor_box(box, image_w: int, image_h: int, args):
    """对过窄或过小的座位锚点做最小尺寸修正。"""
    x1, y1, x2, y2 = box
    cx, cy = box_center(box)
    width = max(x2 - x1, args.min_anchor_width)
    height = max(y2 - y1, args.min_anchor_height)
    width = max(width, height * args.min_anchor_aspect)
    return [
        max(0, round(cx - width / 2, 2)),
        max(0, round(cy - height / 2, 2)),
        min(image_w, round(cx + width / 2, 2)),
        min(image_h, round(cy + height / 2, 2)),
    ]


def expand_box(box, image_w: int, image_h: int, pad: float):
    """按比例扩展检测框并裁剪到图像边界内。"""
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    return [
        max(0, int(round(x1 - w * pad))),
        max(0, int(round(y1 - h * pad))),
        min(image_w, int(round(x2 + w * pad))),
        min(image_h, int(round(y2 + h * pad))),
    ]


def format_time_file(sec: float) -> str:
    """把秒数格式化为适合文件名使用的时间字符串。"""
    sec = int(round(sec))
    return f"{sec // 3600:02d}-{(sec % 3600) // 60:02d}-{sec % 60:02d}"


def make_sahi_model(args):
    """创建 SAHI 使用的 Ultralytics 检测模型。"""
    return AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(MODEL_FILE),
        confidence_threshold=args.conf,
        device=DEVICE,
    )


def predict_people_with_sahi(model, frame, args):
    """使用 SAHI 切片推理检测当前帧中的人员框。"""
    result = get_sliced_prediction(
        frame,
        model,
        slice_height=args.slice_height,
        slice_width=args.slice_width,
        overlap_height_ratio=args.slice_overlap,
        overlap_width_ratio=args.slice_overlap,
        postprocess_type=args.postprocess_type,
        postprocess_match_metric=args.postprocess_match_metric,
        postprocess_match_threshold=args.postprocess_match_threshold,
        verbose=0,
    )

    detections = []
    for pred in result.object_prediction_list:
        category_id = int(pred.category.id)
        if category_id != PERSON_CLASS:
            continue
        x1, y1, x2, y2 = pred.bbox.to_xyxy()
        detections.append(
            {
                "box": [float(x1), float(y1), float(x2), float(y2)],
                "score": float(pred.score.value),
                "category_id": category_id,
            }
        )
    return detections


def add_detection_to_groups(groups, box, score):
    """把当前检测框合并进已有座位组或创建新座位组。"""
    found = None
    for group in groups:
        if same_box(box, group["box"]):
            found = group
            break

    if found is None:
        groups.append({"box": box, "boxes": [box], "scores": [score], "count": 1})
        return

    found["boxes"].append(box)
    found["scores"].append(score)
    found["count"] += 1
    found["box"] = best_box(found["boxes"], found["scores"])


def save_detection_debug_frame(frame, detections, output_file: Path):
    """保存 SAHI 原始检测框调试图，便于排查座位聚合是否漂移。"""
    image = frame.copy()
    for item in detections:
        x1, y1, x2, y2 = [int(round(v)) for v in item["box"]]
        cv2.rectangle(image, (x1, y1), (x2, y2), (60, 220, 60), 1)
        cv2.putText(
            image,
            f"{item['score']:.2f}",
            (x1, max(12, y1 - 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (60, 220, 60),
            1,
            cv2.LINE_AA,
        )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_file), image, [cv2.IMWRITE_JPEG_QUALITY, 95])


def group_rows(groups, row_gap_ratio: float):
    """把座位检测组按照纵向位置聚合为行。"""
    heights = [group["box"][3] - group["box"][1] for group in groups]
    row_gap = (sum(heights) / len(heights)) * row_gap_ratio if heights else 80
    rows = []

    for group in groups:
        cy = box_center(group["box"])[1]
        for row in rows:
            if abs(cy - row["y"]) <= row_gap:
                row["items"].append(group)
                row["y"] = sum(box_center(item["box"])[1] for item in row["items"]) / len(row["items"])
                break
        else:
            rows.append({"y": cy, "items": [group]})

    rows.sort(key=lambda row: row["y"])
    return rows


def build_seats(model, cap, fps: float, duration: float, args, image_w: int, image_h: int):
    """从视频前若干采样帧中使用 SAHI 检测并生成稳定座位列表。"""
    groups = []
    used_count = 0
    sec = args.seat_start

    while sec <= duration and used_count < args.seat_sample_count:
        ret, frame = read_frame_at(cap, fps, sec)
        if not ret or frame is None:
            break

        detections = predict_people_with_sahi(model, frame, args)
        if args.save_debug:
            save_detection_debug_frame(frame, detections, OUTPUT_DIR / "debug_detections" / f"sample_{used_count + 1:02d}_{format_time_file(sec)}.jpg")
        for item in detections:
            add_detection_to_groups(groups, item["box"], item["score"])

        used_count += 1
        sec += args.seat_interval

    min_hits = max(args.min_hits, used_count // 3)
    groups = [group for group in groups if group["count"] >= min_hits]
    groups.sort(key=lambda item: (item["box"][1], item["box"][0]))

    if not groups:
        return []

    seats = []
    seat_id = 1
    for row_index, row in enumerate(group_rows(groups, args.row_gap_ratio), start=1):
        row["items"].sort(key=lambda item: item["box"][0])
        for col_index, group in enumerate(row["items"], start=1):
            box = normalize_anchor_box(group["box"], image_w, image_h, args)
            cx, cy = box_center(box)
            seats.append(
                {
                    "seat_id": seat_id,
                    "seat_code": f"S{seat_id:02d}",
                    "seat_name": f"第{row_index}排第{col_index}列",
                    "row": row_index,
                    "col": col_index,
                    "box": box,
                    "center": [round(cx, 2), round(cy, 2)],
                    "hit_count": group["count"],
                    "avg_conf": round(sum(group["scores"]) / len(group["scores"]), 4),
                }
            )
            seat_id += 1

    return seats


def draw_seat_map(frame, seats, output_file: Path, seat_box_pad: float):
    """在首帧图像上绘制座位编号和放大后的座位框。"""
    image = frame.copy()
    image_h, image_w = image.shape[:2]
    for seat in seats:
        seat_box = expand_box(seat["box"], image_w, image_h, seat_box_pad)
        x1, y1, x2, y2 = [int(round(value)) for value in seat_box]
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 128, 255), 2)
        cv2.rectangle(image, (x1, max(0, y1 - 24)), (x1 + 52, y1), (0, 128, 255), -1)
        cv2.putText(
            image,
            seat["seat_code"],
            (x1 + 5, max(16, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(output_file), image, [cv2.IMWRITE_JPEG_QUALITY, 95])


def save_seat_crops(cap, fps: float, duration: float, seats, output_dir: Path, args):
    """按座位保存后续采样帧中的座位截图。"""
    crops_root = output_dir / "crops"
    records = []
    sec = args.crop_start
    frame_no = 0

    while sec <= duration:
        ret, frame = read_frame_at(cap, fps, sec)
        if not ret or frame is None:
            break

        frame_no += 1
        image_h, image_w = frame.shape[:2]
        for seat in seats:
            # 裁剪区域直接使用座位框 (seat_box)
            seat_box = expand_box(seat["box"], image_w, image_h, args.seat_box_pad)
            x1, y1, x2, y2 = seat_box
            if x2 <= x1 or y2 <= y1:
                continue

            crop = frame[y1:y2, x1:x2].copy()
            seat_dir = crops_root / seat["seat_code"]
            seat_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"{seat['seat_code']}_t{format_time_file(sec)}.jpg"
            file_path = seat_dir / file_name

            # 由于裁剪区域就是座位框，所以在裁剪图中的相对位置就是全图
            rel_original_seat_box = [
                round(seat["box"][0] - x1, 2),
                round(seat["box"][1] - y1, 2),
                round(seat["box"][2] - x1, 2),
                round(seat["box"][3] - y1, 2),
            ]

            cv2.imwrite(str(file_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            records.append(
                {
                    "seat_id": seat["seat_id"],
                    "seat_code": seat["seat_code"],
                    "time_seconds": round(float(sec), 3),
                    "time": format_time_file(sec).replace("-", ":"),
                    "image": str(file_path.relative_to(output_dir)).replace("\\", "/"),
                    "seat_box": seat_box,
                    "seat_box_pad": args.seat_box_pad,
                    "original_seat_box_in_crop": rel_original_seat_box,
                    "source_frame_index": frame_no,
                }
            )

        sec += args.crop_interval

    return records


def parse_args():
    """解析座位检测和截图生成所需的命令行参数。"""
    parser = argparse.ArgumentParser(description="V3 SAHI seat detector: generate per-seat crop images directly from seat boxes.")
    parser.add_argument("--conf", type=float, default=0.15, help="目标检测置信度阈值。")
    parser.add_argument("--slice-height", type=int, default=640, help="SAHI 切片高度，单位为像素。")
    parser.add_argument("--slice-width", type=int, default=640, help="SAHI 切片宽度，单位为像素。")
    parser.add_argument("--slice-overlap", type=float, default=0.4, help="SAHI 切片在宽高方向上的重叠比例。")
    parser.add_argument("--postprocess-type", default="NMS", help="SAHI 后处理类型，常用 NMS 或 GREEDYNMM。")
    parser.add_argument("--postprocess-match-metric", default="IOS", help="SAHI 后处理匹配指标，常用 IOS 或 IOU。")
    parser.add_argument("--postprocess-match-threshold", type=float, default=0.5, help="合并切片重复检测框的匹配阈值。")
    parser.add_argument("--seat-start", type=float, default=0.0, help="用于建立座位锚点的采样起始秒数。")
    parser.add_argument("--seat-interval", type=float, default=1, help="建立座位锚点时的采样帧间隔秒数。")
    parser.add_argument("--seat-sample-count", type=int, default=10, help="用于建立座位锚点的最大采样帧数量。")
    parser.add_argument("--min-hits", type=int, default=5, help="保留一个座位锚点分组所需的最少命中次数。")
    parser.add_argument("--row-gap-ratio", type=float, default=0.65, help="按行聚类时的容差比例，基于平均检测框高度。")
    parser.add_argument("--min-anchor-width", type=float, default=55, help="座位锚点框的最小宽度，避免远处小框或局部窄框导致截图过小。")
    parser.add_argument("--min-anchor-height", type=float, default=80, help="座位锚点框的最小高度，避免只框住头肩或身体局部。")
    parser.add_argument("--min-anchor-aspect", type=float, default=0.45, help="座位锚点最小宽高比，避免生成竖向窄条框。")
    parser.add_argument("--crop-start", type=float, default=0.0, help="保存座位截图的起始秒数。")
    parser.add_argument("--crop-interval", type=float, default=3.0, help="保存座位截图的时间间隔秒数。")
    parser.add_argument("--save-debug", action="store_true", help="保存 SAHI 原始检测框调试图。")
    parser.add_argument(
        "--seat-box-pad",
        type=float,
        default=0.15,
        help="用于裁剪、绘制和 pose 归属判断的座位框扩展比例。",
    )
    parser.add_argument("--clean", action="store_true", help="生成前清空旧的输出目录。")
    return parser.parse_args()


def main():
    """执行 SAHI 座位检测、座位图绘制和座位截图保存流程。"""
    args = parse_args()

    if args.clean and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model = make_sahi_model(args)
    cap = cv2.VideoCapture(str(VIDEO_FILE))
    if not cap.isOpened():
        raise RuntimeError(f"video open failed: {VIDEO_FILE}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps and fps > 0 else 0.0

    ret, first_frame = read_frame_at(cap, fps, 0.0)
    if not ret or first_frame is None:
        raise RuntimeError("cannot read first frame")

    image_h, image_w = first_frame.shape[:2]
    seats = build_seats(model, cap, fps, duration, args, image_w, image_h)
    draw_seat_map(first_frame, seats, OUTPUT_DIR / "seat_map.jpg", args.seat_box_pad)

    crop_records = save_seat_crops(cap, fps, duration, seats, OUTPUT_DIR, args)
    cap.release()

    metadata = {
        "detector": "sahi_v3",
        "video": str(VIDEO_FILE),
        "model": str(MODEL_FILE),
        "output": str(OUTPUT_DIR),
        "person_class": PERSON_CLASS,
        "device": DEVICE,
        "fps": fps,
        "total_frames": total_frames,
        "duration_seconds": round(float(duration), 3),
        "seat_count": len(seats),
        "crop_count": len(crop_records),
        "seat_box_pad": args.seat_box_pad,
        "min_anchor_width": args.min_anchor_width,
        "min_anchor_height": args.min_anchor_height,
        "min_anchor_aspect": args.min_anchor_aspect,
        "slice_height": args.slice_height,
        "slice_width": args.slice_width,
        "slice_overlap": args.slice_overlap,
        "seats": seats,
        "crops": crop_records,
    }
    with open(OUTPUT_DIR / "seats.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"seat_count={len(seats)}")
    print(f"crop_count={len(crop_records)}")
    print(f"output={OUTPUT_DIR}")


if __name__ == "__main__":
    main()
