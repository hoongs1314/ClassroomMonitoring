import argparse
import json
import shutil
from pathlib import Path
from collections import deque

import cv2
import numpy as np
from ultralytics import YOLO


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SEAT_DIR = ROOT_DIR / "outputs/v2/seats_sahi_v3"
DEFAULT_MODEL = ROOT_DIR / "models/yolo26s-pose.pt"
DEFAULT_OUTPUT = ROOT_DIR / "outputs/v2/pose_v4"

# 关键点
HEAD_IDS = [0, 1, 2, 3, 4]
SHOULDER_IDS = [5, 6]

# 状态追踪器配置
WINDOW_SIZE = 5      # 滑动窗口大小（帧数）
MISSING_THRESHOLD = 3 # 允许目标消失的最大帧数（超过则判定为真的 EMPTY）

class SeatTracker:
    """单个座位的状态追踪器，用于平滑检测结果。"""
    def __init__(self, window_size=WINDOW_SIZE):
        self.history = deque(maxlen=window_size)
        self.last_valid_classify = None
        self.missing_count = 0

    def update(self, classify):
        status = classify["status"]
        
        if status == "EMPTY":
            self.missing_count += 1
            # 如果消失帧数在阈值内，且之前有有效状态，则尝试延续之前的状态
            if self.missing_count <= MISSING_THRESHOLD and self.last_valid_classify:
                smoothed_classify = self.last_valid_classify.copy()
                smoothed_classify["reason"] = f"persisted_{smoothed_classify['reason']}"
                return smoothed_classify
            else:
                self.history.append("EMPTY")
                return classify
        else:
            self.missing_count = 0
            self.history.append(status)
            self.last_valid_classify = classify
            
            # 执行投票逻辑 (Majority Vote)
            counts = {}
            for s in self.history:
                counts[s] = counts.get(s, 0) + 1
            
            # 找到出现次数最多的状态
            consensus_status = max(counts, key=counts.get)
            
            # 如果当前状态不是共识状态，且共识状态非常强劲，则修正
            if status != consensus_status and counts[consensus_status] >= (len(self.history) // 2 + 1):
                # 简单起见，这里只修改状态标签，保留原始数据
                smoothed = classify.copy()
                smoothed["status"] = consensus_status
                smoothed["reason"] = f"consensus_{classify['reason']}"
                return smoothed
            
            return classify

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
    return {"id": index, "x": float(kpt_xy[index][0]), "y": float(kpt_xy[index][1]), "conf": conf}

def classify_head_shoulder(kpt_xy, kpt_conf, bbox, args):
    head_points = [visible_point(kpt_xy, kpt_conf, idx, args.kpt_conf) for idx in HEAD_IDS]
    shoulder_points = [visible_point(kpt_xy, kpt_conf, idx, args.kpt_conf) for idx in SHOULDER_IDS]
    head_points = [item for item in head_points if item is not None]
    shoulder_points = [item for item in shoulder_points if item is not None]

    if len(shoulder_points) < 2:
        return {"status": "INVALID", "ratio": None, "reason": "shoulder_low"}

    if not head_points:
        return {"status": "STRONG", "ratio": None, "reason": "head_missing"}

    # 计算均值
    hx = sum(p["x"] for p in head_points) / len(head_points)
    hy = sum(p["y"] for p in head_points) / len(head_points)
    sx = sum(p["x"] for p in shoulder_points) / len(shoulder_points)
    sy = sum(p["y"] for p in shoulder_points) / len(shoulder_points)
    
    bbox_h = max(1.0, bbox[3] - bbox[1])
    ratio = (sy - hy) / bbox_h

    if ratio < args.strong_ratio: status = "STRONG"
    elif ratio < args.weak_ratio: status = "WEAK"
    else: status = "NORMAL"

    return {
        "status": status, 
        "ratio": round(float(ratio), 4), 
        "reason": "ok",
        "head_center": {"x": round(hx, 2), "y": round(hy, 2)},
        "shoulder_center": {"x": round(sx, 2), "y": round(sy, 2)},
        "head_points": head_points,
        "shoulder_points": shoulder_points
    }

def pick_pose(result, seat_box_in_crop, image_shape, args):
    if result.boxes is None or len(result.boxes) == 0: return None
    img_h, img_w = image_shape[:2]
    crop_center_box = [0, 0, img_w, img_h]

    boxes = result.boxes.xyxy
    confs = result.boxes.conf
    kpt_xy = result.keypoints.xy
    kpt_conf = result.keypoints.conf

    candidates = []
    for i in range(len(boxes)):
        box = boxes[i].tolist()
        score = float(confs[i].item())
        overlap = box_overlap_ratio(box, seat_box_in_crop) if seat_box_in_crop else 0.5
        dist = normalized_center_distance(box, crop_center_box)
        
        # 核心关键点平均得分
        main_conf = np.mean([kpt_conf[i][idx].item() for idx in (HEAD_IDS + SHOULDER_IDS)])
        
        # 评分算法
        rank = (overlap * 400) + (main_conf * 200) - (dist * 300) + (score * 100)
        
        candidates.append({
            "rank": rank, "box": box, "conf": score, 
            "overlap": overlap, "dist": dist,
            "kpt_xy": kpt_xy[i].cpu().numpy(), 
            "kpt_conf": kpt_conf[i].cpu().numpy()
        })

    # 过滤尝试
    filtered = [c for c in candidates if c["overlap"] >= 0.15 and c["dist"] <= 0.8]
    if not filtered:
        filtered = candidates # Fallback: 实在没过过滤条件的，选 rank 最高的

    return max(filtered, key=lambda x: x["rank"])

def draw_result(image, picked, classify, output_file: Path):
    canvas = image.copy()
    color_map = {"STRONG": (0,0,255), "WEAK": (0,255,255), "NORMAL": (0,200,0), "INVALID": (160,160,160), "EMPTY": (80,80,80)}
    color = color_map.get(classify["status"], (255,255,255))
    
    if picked:
        x1, y1, x2, y2 = [int(round(v)) for v in picked["box"]]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        if "head_center" in classify:
            hc, sc = classify["head_center"], classify["shoulder_center"]
            cv2.line(canvas, (int(hc["x"]), int(hc["y"])), (int(sc["x"]), int(sc["y"])), color, 2)

    cv2.rectangle(canvas, (0,0), (canvas.shape[1], 30), color, -1)
    label = f"{classify['status']} | {classify.get('ratio', 'N/A')} | {classify['reason']}"
    cv2.putText(canvas, label, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_file), canvas)

def parse_args():
    parser = argparse.ArgumentParser(description="V4 Pose Detector: Temporal Smoothing & Advanced Filtering.")
    parser.add_argument("--seat-dir", type=Path, default=DEFAULT_SEAT_DIR)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--imgsz", type=int, default=1280, help="为了应对小目标，强行拉高输入分辨率。")
    parser.add_argument("--conf", type=float, default=0.20)
    parser.add_argument("--kpt-conf", type=float, default=0.25)
    parser.add_argument("--strong-ratio", type=float, default=-0.10)
    parser.add_argument("--weak-ratio", type=float, default=0.03)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()

def main():
    args = parse_args()
    if args.clean and args.output.exists(): shutil.rmtree(args.output)
    args.output.mkdir(parents=True, exist_ok=True)

    with open(args.seat_dir / "seats.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    model = YOLO(str(args.model))
    trackers = {s["seat_id"]: SeatTracker() for s in data["seats"]}
    seat_map = {s["seat_id"]: s for s in data["seats"]}
    
    # 按照时间顺序对 crops 排序，这对时间平滑至关重要
    crops = sorted(data["crops"], key=lambda x: x["time_seconds"])
    results = []
    
    print(f"V4: Processing {len(crops)} images with temporal smoothing...")
    for i, crop in enumerate(crops):
        if i % 50 == 0: print(f"  Progress: {i}/{len(crops)} ({i/len(crops)*100:.1f}%)")
        
        img = cv2.imread(str(args.seat_dir / crop["image"]))
        if img is None: continue
        
        # 移除任何可能破坏图像特征的预处理
        img_processed = img 

        seat_box = crop.get("original_seat_box_in_crop") or crop.get("seat_box_in_crop")
        res = model.predict(source=img_processed, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]
        
        picked = pick_pose(res, seat_box, img.shape, args)
        
        if picked:
            raw_classify = classify_head_shoulder(picked["kpt_xy"], picked["kpt_conf"], picked["box"], args)
        else:
            raw_classify = {"status": "EMPTY", "reason": "no_pose_person"}
            
        # 应用时间平滑
        smoothed_classify = trackers[crop["seat_id"]].update(raw_classify)
        
        # 保存可视化
        out_path = args.output / "annotated" / crop["seat_code"] / Path(crop["image"]).name
        draw_result(img, picked, smoothed_classify, out_path)
        
        results.append({
            "seat_id": crop["seat_id"], "seat_code": crop["seat_code"],
            "time": crop["time"], "status": smoothed_classify["status"],
            "raw_status": raw_classify["status"], # 记录原始状态以便对比
            "reason": smoothed_classify["reason"]
        })

    with open(args.output / "pose_results_v4.json", "w", encoding="utf-8") as f:
        json.dump({"summary": "V4 results with temporal smoothing", "results": results}, f, indent=2)

    print(f"V4 completed. Output: {args.output}")

if __name__ == "__main__":
    main()
