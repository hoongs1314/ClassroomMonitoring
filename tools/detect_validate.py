import argparse
import json
from pathlib import Path

import cv2
from ultralytics import YOLO

from v1.config import CONF, DETECT_MODEL, IOU, IMG_SIZE, ROOT_DIR


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args():
    parser = argparse.ArgumentParser(description="用 detect 模型做图片验证，并保存每个人的单独截图。")
    parser.add_argument(
        "--model",
        default=str(DETECT_MODEL),
        help="detect 模型路径，默认使用 models/detect.pt",
    )
    parser.add_argument(
        "--source",
        default=str(ROOT_DIR / "inputs/screen"),
        help="输入图片、图片目录，默认扫 inputs 目录",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT_DIR / "outputs" / "detect_validate"),
        help="输出目录",
    )
    parser.add_argument("--imgsz", type=int, default=IMG_SIZE, help="推理尺寸")
    parser.add_argument("--conf", type=float, default=CONF, help="置信度阈值")
    parser.add_argument("--iou", type=float, default=IOU, help="NMS IoU 阈值")
    parser.add_argument(
        "--pad",
        type=float,
        default=0.25,
        help="裁图时给框外再留一点边，0.25 表示各方向额外留 25%",
    )
    parser.add_argument(
        "--person-cls",
        type=int,
        default=None,
        help="只保留某个类别，例如 person 是 0；不传就保存所有检测框",
    )
    return parser.parse_args()


def list_images(source: Path) -> list[Path]:
    if source.is_file():
        return [source]

    images = [path for path in source.rglob("*") if path.suffix.lower() in IMAGE_EXTS]
    return sorted(images)


def make_dirs(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "crops").mkdir(parents=True, exist_ok=True)


def expand_box(box: list[float], width: int, height: int, pad: float) -> list[int]:
    x1, y1, x2, y2 = box
    box_w = x2 - x1
    box_h = y2 - y1
    pad_x = box_w * pad
    pad_y = box_h * pad

    out_x1 = max(0, int(round(x1 - pad_x)))
    out_y1 = max(0, int(round(y1 - pad_y)))
    out_x2 = min(width, int(round(x2 + pad_x)))
    out_y2 = min(height, int(round(y2 + pad_y)))
    return [out_x1, out_y1, out_x2, out_y2]


def pick_color(cls_id: int) -> tuple[int, int, int]:
    base = [
        (0, 255, 255),
        (0, 200, 0),
        (0, 128, 255),
        (255, 128, 0),
        (255, 0, 255),
    ]
    return base[cls_id % len(base)]


def save_one_image(model: YOLO, image_path: Path, out_dir: Path, imgsz: int, conf: float, iou: float, pad: float, person_cls: int | None):
    image = cv2.imread(str(image_path))
    if image is None:
        return None

    result = model.predict(
        source=image,
        imgsz=imgsz,
        conf=conf,
        iou=iou,
        verbose=False,
    )[0]

    draw = image.copy()
    image_h, image_w = image.shape[:2]
    image_name = image_path.stem
    crop_dir = out_dir / "crops" / image_name
    crop_dir.mkdir(parents=True, exist_ok=True)

    items = []
    names = result.names or {}
    boxes = result.boxes
    if boxes is None:
        boxes = []

    person_index = 0
    for idx in range(len(boxes)):
        cls_id = int(boxes.cls[idx].item()) if boxes.cls is not None else 0
        if person_cls is not None and cls_id != person_cls:
            continue

        person_index += 1
        box = [float(v) for v in boxes.xyxy[idx].tolist()]
        score = float(boxes.conf[idx].item()) if boxes.conf is not None else 0.0
        x1, y1, x2, y2 = [int(round(v)) for v in box]
        cut_x1, cut_y1, cut_x2, cut_y2 = expand_box(box, image_w, image_h, pad)
        crop = image[cut_y1:cut_y2, cut_x1:cut_x2].copy()

        color = pick_color(cls_id)
        cv2.rectangle(draw, (x1, y1), (x2, y2), color, 2)

        label = f"ID {person_index} {names.get(cls_id, str(cls_id))} {score:.2f}"
        cv2.putText(
            draw,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            color,
            2,
            cv2.LINE_AA,
        )

        cv2.rectangle(
            crop,
            (x1 - cut_x1, y1 - cut_y1),
            (x2 - cut_x1, y2 - cut_y1),
            color,
            2,
        )

        crop_file = crop_dir / f"{person_index:03d}.jpg"
        cv2.imwrite(str(crop_file), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])

        items.append(
            {
                "id": person_index,
                "class_id": cls_id,
                "class_name": names.get(cls_id, str(cls_id)),
                "conf": round(score, 4),
                "bbox": [round(v, 2) for v in box],
                "crop_bbox": [cut_x1, cut_y1, cut_x2, cut_y2],
                "crop_file": str(crop_file.relative_to(out_dir)).replace("\\", "/"),
            }
        )

    draw_file = out_dir / "images" / f"{image_name}_detect.jpg"
    cv2.imwrite(str(draw_file), draw, [cv2.IMWRITE_JPEG_QUALITY, 95])

    return {
        "image_file": str(image_path.relative_to(ROOT_DIR)).replace("\\", "/") if image_path.is_relative_to(ROOT_DIR) else str(image_path),
        "draw_file": str(draw_file.relative_to(out_dir)).replace("\\", "/"),
        "count": len(items),
        "items": items,
    }


def main():
    args = parse_args()
    model_path = Path(args.model)
    source_path = Path(args.source)
    out_dir = Path(args.out)

    if not model_path.exists():
        raise FileNotFoundError(f"模型不存在：{model_path}")
    if not source_path.exists():
        raise FileNotFoundError(f"输入不存在：{source_path}")

    make_dirs(out_dir)
    model = YOLO(str(model_path))
    image_list = list_images(source_path)
    if not image_list:
        raise RuntimeError(f"没找到可处理的图片：{source_path}")

    results = []
    for image_path in image_list:
        one = save_one_image(
            model=model,
            image_path=image_path,
            out_dir=out_dir,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            pad=args.pad,
            person_cls=args.person_cls,
        )
        if one is not None:
            results.append(one)
            print(f"{one['image_file']} -> 检出 {one['count']} 人")

    json_file = out_dir / "result.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": str(model_path),
                "source": str(source_path),
                "imgsz": args.imgsz,
                "conf": args.conf,
                "iou": args.iou,
                "pad": args.pad,
                "person_cls": args.person_cls,
                "images": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\n验证完成，结果目录：{out_dir}")
    print(f"标注图目录：{out_dir / 'images'}")
    print(f"人物裁图目录：{out_dir / 'crops'}")
    print(f"结果 JSON：{json_file}")


if __name__ == "__main__":
    main()
