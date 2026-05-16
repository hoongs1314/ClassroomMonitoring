import numpy as np
from ultralytics import YOLO

class PoseEngine:
    def __init__(self, model_path, device="cpu"):
        self.model = YOLO(model_path)
        self.head_ids = [0, 1, 2, 3, 4]
        self.shoulder_ids = [5, 6]

    def detect_poses_batch(self, frame, seats, imgsz=640):
        if not seats:
            return []

        crops = []
        pad = 20
        h, w = frame.shape[:2]
        
        for s in seats:
            x1, y1, x2, y2 = [int(v) for v in s["box"]]
            crop = frame[max(0, y1-pad):min(h, y2+pad), max(0, x1-pad):min(w, x2+pad)]
            if crop.size == 0:
                crops.append(np.zeros((100, 100, 3), dtype=np.uint8))
            else:
                crops.append(crop)

        results_list = self.model.predict(source=crops, imgsz=imgsz, conf=0.20, verbose=False)
        
        final_results = []
        for i, results in enumerate(results_list):
            if not results.boxes or len(results.boxes) == 0:
                final_results.append(("UNCERTAIN", 0.0))
                continue

            ch, cw = crops[i].shape[:2]
            best_idx = 0
            if len(results.boxes) > 1:
                dists = []
                for b in results.boxes.xywh:
                    dists.append((b[0].item() - cw/2)**2 + (b[1].item() - ch/2)**2)
                best_idx = np.argmin(dists)

            kpts = results.keypoints.xy[best_idx].cpu().numpy()
            confs = results.keypoints.conf[best_idx].cpu().numpy()

            visible_heads = [j for j in self.head_ids if confs[j] > 0.45]
            visible_shoulders = [j for j in self.shoulder_ids if confs[j] > 0.45]

            if len(visible_shoulders) < 2 or len(visible_heads) < 2:
                final_results.append(("SUSPECTED", float(np.mean(confs))))
                continue

            hy = np.mean([kpts[j][1] for j in visible_heads])
            sy = np.mean([kpts[j][1] for j in visible_shoulders])
            bh = max(1.0, results.boxes.xyxy[best_idx][3].item() - results.boxes.xyxy[best_idx][1].item())
            ratio = (sy - hy) / bh

            if 0.05 < ratio < 0.25:
                final_results.append(("NORMAL", float(np.mean(confs))))
            else:
                final_results.append(("SUSPECTED", float(np.mean(confs))))

        return final_results
