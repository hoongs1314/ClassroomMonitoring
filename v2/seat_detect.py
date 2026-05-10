import argparse
import json
import shutil
from pathlib import Path

import cv2
from ultralytics import YOLO


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = ROOT_DIR / "inputs" / "video" / "test.mp4"
DEFAULT_MODEL = ROOT_DIR / "models" / "detect.pt"
DEFAULT_OUTPUT = ROOT_DIR / "outputs" / "v2" / "seats"


def read_frame_at(cap, fps: float, sec: float):
    if fps <= 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
    else:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(sec * fps)))
    return cap.read()


def box_center(box):
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def same_box(box1, box2) -> bool:
    x1, y1 = box_center(box1)
    x2, y2 = box_center(box2)
    w = max(40.0, min(box1[2] - box1[0], box2[2] - box2[0]))
    h = max(60.0, min(box1[3] - box1[1], box2[3] - box2[1]))
    return abs(x1 - x2) <= w * 0.7 and abs(y1 - y2) <= h * 0.8


def avg_box(box_list):
    size = len(box_list)
    return [
        round(sum(box[0] for box in box_list) / size, 2),
        round(sum(box[1] for box in box_list) / size, 2),
        round(sum(box[2] for box in box_list) / size, 2),
        round(sum(box[3] for box in box_list) / size, 2),
    ]


def expand_box(box, image_w: int, image_h: int, pad: float):
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
    sec = int(round(sec))
    return f"{sec // 3600:02d}-{(sec % 3600) // 60:02d}-{sec % 60:02d}"


def build_seats(model, cap, fps: float, duration: float, args):
    groups = []
    used_count = 0
    sec = args.seat_start

    while sec <= duration and used_count < args.seat_sample_count:
        ret, frame = read_frame_at(cap, fps, sec)
        if not ret or frame is None:
            break

        result = model.predict(
            source=frame,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            verbose=False,
        )[0]

        if result.boxes is not None:
            boxes = result.boxes.xyxy.tolist()
            confs = result.boxes.conf.tolist() if result.boxes.conf is not None else [0.0] * len(boxes)
            classes = result.boxes.cls.tolist() if result.boxes.cls is not None else [0] * len(boxes)

            for index, box in enumerate(boxes):
                if int(classes[index]) != args.person_class:
                    continue

                score = float(confs[index])
                found = None
                for group in groups:
                    if same_box(box, group["box"]):
                        found = group
                        break

                if found is None:
                    groups.append({"box": box, "boxes": [box], "scores": [score], "count": 1})
                else:
                    found["boxes"].append(box)
                    found["scores"].append(score)
                    found["count"] += 1
                    found["box"] = avg_box(found["boxes"])

        used_count += 1
        sec += args.seat_interval

    min_hits = max(args.min_hits, used_count // 3)
    groups = [group for group in groups if group["count"] >= min_hits]
    groups.sort(key=lambda item: (item["box"][1], item["box"][0]))

    if not groups:
        return []

    heights = [group["box"][3] - group["box"][1] for group in groups]
    row_gap = (sum(heights) / len(heights)) * args.row_gap_ratio
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

    seats = []
    seat_id = 1
    for row_index, row in enumerate(rows, start=1):
        row["items"].sort(key=lambda item: item["box"][0])
        for col_index, group in enumerate(row["items"], start=1):
            box = avg_box(group["boxes"])
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
            crop_box = expand_box(seat["box"], image_w, image_h, args.crop_pad)
            seat_box = expand_box(seat["box"], image_w, image_h, args.seat_box_pad)
            x1, y1, x2, y2 = crop_box
            if x2 <= x1 or y2 <= y1:
                continue

            crop = frame[y1:y2, x1:x2].copy()
            seat_dir = crops_root / seat["seat_code"]
            seat_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"{seat['seat_code']}_t{format_time_file(sec)}.jpg"
            file_path = seat_dir / file_name

            rel_seat_box = [
                round(seat_box[0] - x1, 2),
                round(seat_box[1] - y1, 2),
                round(seat_box[2] - x1, 2),
                round(seat_box[3] - y1, 2),
            ]
            rel_original_seat_box = [
                round(seat["box"][0] - x1, 2),
                round(seat["box"][1] - y1, 2),
                round(seat["box"][2] - x1, 2),
                round(seat["box"][3] - y1, 2),
            ]
            cv2.rectangle(
                crop,
                (int(rel_seat_box[0]), int(rel_seat_box[1])),
                (int(rel_seat_box[2]), int(rel_seat_box[3])),
                (0, 128, 255),
                2,
            )
            cv2.imwrite(str(file_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            records.append(
                {
                    "seat_id": seat["seat_id"],
                    "seat_code": seat["seat_code"],
                    "time_seconds": round(float(sec), 3),
                    "time": format_time_file(sec).replace("-", ":"),
                    "image": str(file_path.relative_to(output_dir)).replace("\\", "/"),
                    "crop_box": crop_box,
                    "crop_pad": args.crop_pad,
                    "seat_box": seat_box,
                    "seat_box_pad": args.seat_box_pad,
                    "seat_box_in_crop": rel_seat_box,
                    "original_seat_box_in_crop": rel_original_seat_box,
                    "source_frame_index": frame_no,
                }
            )

        sec += args.crop_interval

    return records


def parse_args():
    parser = argparse.ArgumentParser(description="V2 seat detector: generate per-seat crop images from a classroom video.")
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--imgsz", type=int, default=3200)
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--iou", type=float, default=0.6)
    parser.add_argument("--person-class", type=int, default=0)
    parser.add_argument("--seat-start", type=float, default=0.0)
    parser.add_argument("--seat-interval", type=float, default=1.0)
    parser.add_argument("--seat-sample-count", type=int, default=10)
    parser.add_argument("--min-hits", type=int, default=2)
    parser.add_argument("--row-gap-ratio", type=float, default=0.65)
    parser.add_argument("--crop-start", type=float, default=0.0)
    parser.add_argument("--crop-interval", type=float, default=3.0)
    parser.add_argument(
        "--crop-pad",
        type=float,
        default=0.9,
        help="Expand each side by this ratio. 0.9 means final crop is about 2.8x seat width/height.",
    )
    parser.add_argument(
        "--seat-box-pad",
        type=float,
        default=0.3,
        help="Expand the seat box used for drawing and pose ownership. 0.5 means about 2x seat width/height.",
    )
    parser.add_argument("--clean", action="store_true", help="Remove old output before generating crops.")
    return parser.parse_args()


def main():
    args = parse_args()
    video_file = args.video if args.video.is_absolute() else ROOT_DIR / args.video
    model_file = args.model if args.model.is_absolute() else ROOT_DIR / args.model
    output_dir = args.output if args.output.is_absolute() else ROOT_DIR / args.output

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(model_file))
    cap = cv2.VideoCapture(str(video_file))
    if not cap.isOpened():
        raise RuntimeError(f"video open failed: {video_file}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps and fps > 0 else 0.0

    seats = build_seats(model, cap, fps, duration, args)
    ret, first_frame = read_frame_at(cap, fps, 0.0)
    if ret and first_frame is not None:
        draw_seat_map(first_frame, seats, output_dir / "seat_map.jpg", args.seat_box_pad)

    crop_records = save_seat_crops(cap, fps, duration, seats, output_dir, args)
    cap.release()

    metadata = {
        "video": str(video_file.relative_to(ROOT_DIR)).replace("\\", "/") if video_file.is_relative_to(ROOT_DIR) else str(video_file),
        "model": str(model_file.relative_to(ROOT_DIR)).replace("\\", "/") if model_file.is_relative_to(ROOT_DIR) else str(model_file),
        "fps": fps,
        "total_frames": total_frames,
        "duration_seconds": round(float(duration), 3),
        "seat_count": len(seats),
        "crop_count": len(crop_records),
        "crop_pad": args.crop_pad,
        "seat_box_pad": args.seat_box_pad,
        "seats": seats,
        "crops": crop_records,
    }
    with open(output_dir / "seats.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"seat_count={len(seats)}")
    print(f"crop_count={len(crop_records)}")
    print(f"output={output_dir}")


if __name__ == "__main__":
    main()
