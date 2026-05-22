import logging
import time

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger("monitor.pose")


class PoseEngine:
    def __init__(self, model_path):
        self.model = YOLO(model_path)

        # 0 left_eye, 1 right_eye, 2 nose, 3 left_ear, 4 right_ear
        # 5 left_shoulder, 6 right_shoulder
        # 7 left_elbow, 8 right_elbow
        self.head_ids = [0, 1, 2, 3, 4]
        self.shoulder_ids = [5, 6]
        self.elbow_ids = [7, 8]
        self.head_min_conf = 0.50
        self.shoulder_min_conf = 0.35
        self.head_min_count = 2
        self.shoulder_min_count = 2

    def detect_poses_batch(self, frame, seats):
        """批量姿态检测"""
        if not seats:
            return []

        crops = []
        h, w = frame.shape[:2]

        for s in seats:
            x1, y1, x2, y2 = [int(v) for v in s["box"]]
            box_w = max(1, x2 - x1)
            box_h = max(1, y2 - y1)
            pad = min(80, max(40, int(max(box_w, box_h) * 0.5)))
            crop = frame[
                max(0, y1 - pad):min(h, y2 + pad),
                max(0, x1 - pad):min(w, x2 + pad)
            ]

            if crop.size == 0:
                crops.append(np.zeros((100, 100, 3), dtype=np.uint8))
            else:
                crops.append(crop)

        start = time.time()
        results_list = self.model.predict(
            source=crops,
            imgsz=640,
            conf=0.30,
            iou=0.2,
            verbose=False
        )
        end = time.time()

        # 普通 info 日志不要加 exc_info=True
        logger.info("[Pose] 模型检测耗时 %.4f 秒", end - start)

        final_results = []

        for i, results in enumerate(results_list):
            if results.boxes is None or len(results.boxes) == 0:
                final_results.append(("UNCERTAIN", 0.0, 0.0, 0.0))
                continue

            if results.keypoints is None or results.keypoints.xy is None:
                final_results.append(("UNCERTAIN", 0.0, 0.0, 0.0))
                continue

            ch, cw = crops[i].shape[:2]

            # 多个人体框时，选择最靠近 crop 中心的框
            best_idx = 0
            if len(results.boxes) > 1:
                dists = []
                for b in results.boxes.xywh:
                    dx = b[0].item() - cw / 2
                    dy = b[1].item() - ch / 2
                    dists.append(dx * dx + dy * dy)
                best_idx = int(np.argmin(dists))

            kpts = results.keypoints.xy[best_idx].cpu().numpy()
            confs = results.keypoints.conf[best_idx].cpu().numpy()

            visible_heads = [j for j in self.head_ids if confs[j] > self.head_min_conf]
            visible_shoulders = [j for j in self.shoulder_ids if confs[j] > self.shoulder_min_conf]

            keypoint_conf = float(np.mean(confs))

            if len(visible_shoulders) < self.shoulder_min_count or len(visible_heads) < self.head_min_count:
                final_results.append(("UNCERTAIN", keypoint_conf, 0.0, keypoint_conf))
                continue

            hy = np.mean([kpts[j][1] for j in visible_heads])
            sy = np.mean([kpts[j][1] for j in visible_shoulders])

            box = results.boxes.xyxy[best_idx]
            bh = max(1.0, box[3].item() - box[1].item())

            # sy - hy 越大，说明头部越明显在肩膀上方
            # ratio 越小，说明头部越靠近肩线，可能低头/趴桌/遮挡
            ratio = (sy - hy) / bh

            if 0.05 < ratio < 0.35:
                final_results.append(("NORMAL", keypoint_conf, float(ratio), keypoint_conf))
            else:
                final_results.append(("SUSPECTED", keypoint_conf, float(ratio), keypoint_conf))

        return final_results
