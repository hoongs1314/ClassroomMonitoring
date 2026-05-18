import os
import json
import logging
import base64
import time
import cv2
import queue
import numpy as np
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from video_stream_util import MockMonitorStream
from pose_engine import PoseEngine

ROOT_PATH = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_PATH / "outputs/final"
EVENT_CROP_DIR = OUTPUT_DIR / "event_crops"
LOG_DIR = OUTPUT_DIR / "analysis_logs"
REVIEW_INPUT_DIR = OUTPUT_DIR / "review_inputs"
RUN_LOG_DIR = ROOT_PATH / "outputs" / "logs"

EVENT_CROP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
REVIEW_INPUT_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("monitor")
logger.setLevel(logging.DEBUG)

_fh = logging.FileHandler(str(RUN_LOG_DIR / "monitor.log"), encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%m-%d %H:%M:%S"
))
logger.addHandler(_fh)

_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S"
))
logger.addHandler(_ch)

logger.info("===== 系统启动 =====")

# ── 班级配置 ──
CLASS_VIDEOS = {
    "1班": ROOT_PATH / "inputs/video/test.mp4",
    "2班": ROOT_PATH / "inputs/video/v1.mp4",
    "3班": ROOT_PATH / "inputs/video/v2.mp4",
    "4班": ROOT_PATH / "inputs/video/v3.mp4",
}
DEFAULT_CLASS = "1班"

def _get_video_dims(video_path):
    cap = cv2.VideoCapture(str(video_path))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    logger.debug("视频尺寸: %s → %dx%d", Path(video_path).name, w, h)
    return w, h

video_stream = MockMonitorStream(CLASS_VIDEOS[DEFAULT_CLASS])
initial_frame = video_stream.get_latest_frame()
IMG_W, IMG_H = _get_video_dims(CLASS_VIDEOS[DEFAULT_CLASS])
logger.info("默认班级: %s, 尺寸: %dx%d", DEFAULT_CLASS, IMG_W, IMG_H)

state = {
    "is_running": False,
    "time": "00:00:00",
    "frame": initial_frame,
    "img_w": IMG_W,
    "img_h": IMG_H,
    "current_class": DEFAULT_CLASS,
    "class_list": list(CLASS_VIDEOS.keys()),
    "seats": [],
    "events": [],
    "counts": {"total": 0, "focus": 0, "normal": 0},
}

def reset_detection_state():
    suspect_hits.clear()
    recover_hits.clear()
    review_last_at.clear()
    review_pending.clear()
    locked_at.clear()
    while not review_queue.empty():
        try:
            review_queue.get_nowait()
        except queue.Empty:
            break
    state["seats"] = []
    state["events"] = []
    state["counts"] = {"total": 0, "focus": 0, "normal": 0}
    logger.info("检测状态已重置")

def switch_class(class_name):
    if class_name not in CLASS_VIDEOS:
        logger.warning("无效班级: %s", class_name)
        return False
    video_path = CLASS_VIDEOS[class_name]
    logger.info("切换班级: %s → %s", class_name, video_path.name)
    video_stream.switch_video(video_path)
    state["current_class"] = class_name
    state["img_w"], state["img_h"] = _get_video_dims(video_path)
    state["frame"] = video_stream.get_latest_frame()
    reset_detection_state()
    return True

# ── 共享状态 ──
websocket_clients = set()
review_queue = queue.Queue(maxsize=12)
review_last_at = {}
review_pending = set()
suspect_hits = {}
recover_hits = {}
locked_at = {}

# ── 常量 ──
SUSPECT_CONFIRM_COUNT = 2
REVIEW_COOLDOWN_SECONDS = 10
REVIEW_CROP_PAD = 8
EVENT_CROP_PAD = 20
RECOVER_CONFIRM_COUNT = 2
MIN_LOCK_SECONDS = 30
VLM_BATCH_MAX = 6
COLD_START_CYCLES = 8

# ── 工具函数 ──
def box_center(box):
    return (box[2] + box[0]) / 2, (box[3] + box[1]) / 2

def box_distance_sq(box_a, box_b):
    ax, ay = box_center(box_a)
    bx, by = box_center(box_b)
    return (ax - bx) ** 2 + (ay - by) ** 2

def box_iou(box_a, box_b):
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0

def find_current_seat(ans, review_seats):
    target_id = ans.get("seat_id")
    review_seat = next((s for s in review_seats if s["seat_id"] == target_id), None)

    # 先按 seat_id 匹配
    for s in state["seats"]:
        if s["seat_id"] == target_id:
            return s, review_seat or s

    # seat_id 不匹配 → 按 review_seat 信息找
    if review_seat:
        for s in state["seats"]:
            if s["seat_code"] == review_seat["seat_code"]:
                return s, review_seat
        # IoU 兜底
        best_s, best_iou = None, 0
        for s in state["seats"]:
            iou = box_iou(s["box"], review_seat["box"])
            if iou > best_iou:
                best_iou = iou
                best_s = s
        if best_s and best_iou > 0.3:
            return best_s, review_seat
        # 距离兜底
        nearest, nearest_dist = None, None
        for s in state["seats"]:
            dist = box_distance_sq(s["box"], review_seat["box"])
            if nearest_dist is None or dist < nearest_dist:
                nearest, nearest_dist = s, dist
        if nearest and nearest_dist < 9000:
            return nearest, review_seat

    return None, review_seat

def build_review_sheet(frame, seats):
    cell_w, cell_h = 320, 240
    cols = min(3, len(seats))
    rows = (len(seats) + cols - 1) // cols
    sheet = 255 * np.ones((rows * cell_h, cols * cell_w, 3), dtype="uint8")
    targets_text = ""
    h, w = frame.shape[:2]

    for i, s in enumerate(seats):
        bx = s["box"]
        x1, x2 = max(0, int(bx[0]) - REVIEW_CROP_PAD), min(w, int(bx[2]) + REVIEW_CROP_PAD)
        y1, y2 = max(0, int(bx[1]) - REVIEW_CROP_PAD), min(h, int(bx[3]) + REVIEW_CROP_PAD)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        scale = min((cell_w - 20) / crop.shape[1], (cell_h - 42) / crop.shape[0])
        resized_w = max(1, int(crop.shape[1] * scale))
        resized_h = max(1, int(crop.shape[0] * scale))
        resized = cv2.resize(crop, (resized_w, resized_h))
        row, col = divmod(i, cols)
        top = row * cell_h + 34
        left = col * cell_w + 10
        sheet[top:top + resized_h, left:left + resized_w] = resized
        # 只显示纯数字 ID，避免 VLM 混淆
        label = f"ID:{s['seat_id']}"
        cv2.putText(sheet, label, (col * cell_w + 10, row * cell_h + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        targets_text += f"- seat_id: {s['seat_id']}, code: {s['seat_code']}\n"

    return sheet, targets_text

def parse_model_json(response):
    content = response.strip().strip("```json").strip("```").strip()
    if not content.startswith("["):
        start = content.find("[")
        end = content.rfind("]")
        if start >= 0 and end > start:
            content = content[start:end + 1]
    return json.loads(content)

def apply_review_result(response, answers, frame, review_seats, ts_ms, input_image_path):
    with open(LOG_DIR / f"audit_{ts_ms}.json", "w", encoding="utf-8") as f_log:
        json.dump({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "input_image": str(input_image_path),
            "raw": response,
        }, f_log, ensure_ascii=False, indent=2)

    for ans in answers:
        s_obj, review_seat = find_current_seat(ans, review_seats)
        target = s_obj or review_seat
        if not target:
            logger.warning("[VLM结果] seat_id=%s 未匹配到当前座位", ans.get("seat_id"))
            continue

        if s_obj:
            s_obj["status"] = ans["status"]
            if ans["status"] in ("HEAD_DOWN", "DESK_LYING"):
                s_obj["locked_abnormal"] = True
                locked_at[s_obj["seat_id"]] = time.time()
            else:
                s_obj["locked_abnormal"] = False
                locked_at.pop(s_obj["seat_id"], None)

        if ans["status"] in ("HEAD_DOWN", "DESK_LYING"):
            file_name = f"ev_{ts_ms}_{target['seat_code']}.jpg"
            bx = target["box"]
            y1, y2 = max(0, int(bx[1]) - EVENT_CROP_PAD), min(state["img_h"], int(bx[3]) + EVENT_CROP_PAD)
            x1, x2 = max(0, int(bx[0]) - EVENT_CROP_PAD), min(state["img_w"], int(bx[2]) + EVENT_CROP_PAD)
            cv2.imwrite(str(EVENT_CROP_DIR / file_name), frame[y1:y2, x1:x2])
            state["events"].insert(0, {
                "id": time.time(),
                "time": time.strftime("%H:%M:%S"),
                "seat": target["seat_code"],
                "label": ans["label"],
                "reason": ans["reason"],
                "risk": "高" if ans.get("risk_level") == "HIGH" else "中",
                "url": f"/event_crops/{file_name}",
                "full_ans": response,
                "box": bx,
            })
            logger.info("[VLM结果] 异常确认 seat=%s status=%s label=%s risk=%s",
                        target["seat_code"], ans["status"], ans["label"], ans.get("risk_level", "?"))
        else:
            logger.debug("[VLM结果] seat=%s status=%s conf=%.2f",
                         target["seat_code"], ans["status"], ans.get("confidence", 0))

def enqueue_review(frame, seats):
    now = time.time()
    targets = []
    skipped_locked = 0
    skipped_pending = 0

    for s in seats:
        sid = s["seat_id"]
        # 去重：已锁定或已在队列中
        if s.get("locked_abnormal"):
            skipped_locked += 1
            continue
        if sid in review_pending:
            skipped_pending += 1
            continue
        last_at = review_last_at.get(sid, 0)
        if now - last_at < REVIEW_COOLDOWN_SECONDS:
            continue
        targets.append(dict(s))

    if skipped_locked or skipped_pending:
        logger.debug("[VLM入队] 跳过: locked=%d pending=%d", skipped_locked, skipped_pending)

    if not targets:
        return

    # 分批，每批最多 VLM_BATCH_MAX 个
    for start in range(0, len(targets), VLM_BATCH_MAX):
        batch = targets[start:start + VLM_BATCH_MAX]
        for s in batch:
            review_pending.add(s["seat_id"])
        job = {"frame": frame.copy(), "seats": batch}
        try:
            review_queue.put(job, block=True, timeout=3)
            for s in batch:
                review_last_at[s["seat_id"]] = now
            logger.info("[VLM入队] %d个座位: %s",
                        len(batch), ", ".join(f"{s['seat_code']}({s['status']})" for s in batch))
        except queue.Full:
            for s in batch:
                review_pending.discard(s["seat_id"])
            logger.warning("[VLM入队] 队列满，丢弃%d个: %s",
                           len(batch), [s["seat_code"] for s in batch])

def make_vlm_worker(worker_id):
    """创建独立 VLM worker，共享 review_queue"""
    def run():
        api_key = os.environ.get("ALIYUN_API_KEY")
        if not api_key:
            logger.warning("[VLM-w%d] ALIYUN_API_KEY 未设置", worker_id)

        vlm = ChatOpenAI(
            model="qwen-vl-max",
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        sys_content = (ROOT_PATH / "vlm_system_prompt.md").read_text(encoding="utf-8")
        usr_tmpl = (ROOT_PATH / "vlm_user_prompt.md").read_text(encoding="utf-8")
        logger.info("[VLM-w%d] 就绪", worker_id)

        while True:
            job = review_queue.get()
            if not state["is_running"]:
                for s in job["seats"]:
                    review_pending.discard(s["seat_id"])
                continue

            t0 = time.time()
            seat_ids = [s["seat_id"] for s in job["seats"]]
            logger.info("[VLM-w%d] 开始复核 %d个: %s", worker_id, len(job["seats"]), seat_ids)

            try:
                sheet, targets_text = build_review_sheet(job["frame"], job["seats"])
                ts_ms = int(time.time() * 1000)
                img_path = REVIEW_INPUT_DIR / f"review_{ts_ms}.jpg"
                cv2.imwrite(str(img_path), sheet)
                ok, buf = cv2.imencode('.jpg', sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ok:
                    logger.error("[VLM-w%d] 图片编码失败", worker_id)
                    for s in job["seats"]:
                        review_pending.discard(s["seat_id"])
                    continue

                img_b64 = base64.b64encode(buf).decode('utf-8')
                user_msg = usr_tmpl.replace("{{targets_info}}", targets_text)
                resp = vlm.invoke([
                    SystemMessage(content=sys_content),
                    HumanMessage(content=[
                        {"type": "text", "text": user_msg},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    ]),
                ]).content
                logger.info("[VLM-w%d] 完成 耗时%.1fs", worker_id, time.time() - t0)

                if state["is_running"]:
                    answers = parse_model_json(resp)
                    logger.debug("[VLM-w%d] 解析到%d条结果", worker_id, len(answers))
                    apply_review_result(resp, answers, job["frame"], job["seats"], ts_ms, img_path)
            except Exception as e:
                logger.error("[VLM-w%d] 异常(%.1fs): %s", worker_id, time.time() - t0, e, exc_info=True)
            finally:
                for s in job["seats"]:
                    review_pending.discard(s["seat_id"])

    return run

# ── 检测主循环 ──
def detection_analysis_loop():
    logger.info("[检测引擎] 正在初始化模型...")

    detector = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(ROOT_PATH / "models" / "detect.pt"),
        confidence_threshold=0.25,
    )
    logger.info("[检测引擎] SAHI人体检测模型加载完成")

    pose_model = PoseEngine(str(ROOT_PATH / "models" / "yolo26s-pose.pt"))
    logger.info("[检测引擎] Pose姿态模型加载完成，进入主循环")

    cycle_index = 0
    seat_id_counter = 100
    _log_interval = 30

    while True:
        if not state["is_running"]:
            time.sleep(0.5)
            continue

        frame = state["frame"]
        if frame is None:
            time.sleep(0.05)
            continue

        prediction = get_sliced_prediction(
            frame, detector,
            slice_height=640, slice_width=640, verbose=0,
        )

        detections = [p for p in prediction.object_prediction_list if p.category.id == 0]
        new_seats = []
        used_ids = set()
        matched_n = 0
        new_n = 0

        for det in detections:
            raw_box = det.bbox.to_xyxy()
            box_xyxy = [round(raw_box[0], 2), round(raw_box[1], 2),
                        round(raw_box[2], 2), round(raw_box[3], 2)]

            # IoU + 距离双重匹配
            best_match, best_iou = None, 0
            for s in state["seats"]:
                if s["seat_id"] in used_ids:
                    continue
                iou = box_iou(box_xyxy, s["box"])
                dist_sq = box_distance_sq(box_xyxy, s["box"])
                if iou > 0.3 or dist_sq < 5000:
                    if iou > best_iou:
                        best_iou = iou
                        best_match = s

            if best_match:
                used_ids.add(best_match["seat_id"])
                best_match["box"] = box_xyxy
                new_seats.append(best_match)
                matched_n += 1
            else:
                # 避免与刚新增的座位重复
                if any(box_iou(box_xyxy, s["box"]) > 0.5 for s in new_seats):
                    continue
                seat_id_counter += 1
                new_seats.append({
                    "seat_id": seat_id_counter,
                    "seat_code": f"S{seat_id_counter - 100:02d}",
                    "box": box_xyxy,
                    "status": "NORMAL",
                    "locked_abnormal": False,
                })
                new_n += 1

        new_seats.sort(key=lambda s: s["seat_id"])
        state["seats"] = new_seats

        # Pose 检测 —— 每 3 个周期一次
        if cycle_index % 3 == 0 and state["seats"]:
            poses = pose_model.detect_poses_batch(frame, state["seats"])
            suspected = []
            high_conf_direct = []
            pose_summary = {"NORMAL": 0, "SUSPECTED": 0, "UNCERTAIN": 0}

            for i, (p_status, p_conf, ratio, kp_conf) in enumerate(poses):
                if i >= len(state["seats"]):
                    break
                s = state["seats"][i]
                pose_summary[p_status] = pose_summary.get(p_status, 0) + 1

                if p_status in ("SUSPECTED", "UNCERTAIN"):
                    # 方案B：高置信直判，跳过 VLM
                    if p_status == "SUSPECTED" and ratio < 0.03 and kp_conf > 0.55:
                        s["status"] = "HEAD_DOWN"
                        s["locked_abnormal"] = True
                        locked_at[s["seat_id"]] = time.time()
                        high_conf_direct.append(s["seat_code"])
                        suspect_hits[s["seat_id"]] = 0
                        continue

                    if not s.get("locked_abnormal"):
                        s["status"] = p_status
                    suspect_hits[s["seat_id"]] = suspect_hits.get(s["seat_id"], 0) + 1
                    recover_hits[s["seat_id"]] = 0
                    if suspect_hits[s["seat_id"]] >= SUSPECT_CONFIRM_COUNT:
                        suspected.append(s)
                else:
                    suspect_hits[s["seat_id"]] = 0
                    if not s.get("locked_abnormal"):
                        s["status"] = p_status
                    else:
                        # 恢复检查：需满足最小锁定时间
                        lock_ts = locked_at.get(s["seat_id"], 0)
                        if time.time() - lock_ts < MIN_LOCK_SECONDS:
                            continue
                        recover_hits[s["seat_id"]] = recover_hits.get(s["seat_id"], 0) + 1
                        if recover_hits[s["seat_id"]] >= RECOVER_CONFIRM_COUNT:
                            s["locked_abnormal"] = False
                            s["status"] = p_status
                            locked_at.pop(s["seat_id"], None)
                            logger.info("[恢复] seat=%s 解除锁定", s["seat_code"])

            if high_conf_direct:
                logger.info("[高置信直判] %d个: %s", len(high_conf_direct), high_conf_direct)

            # 冷启动期间不送 VLM
            if suspected and cycle_index >= COLD_START_CYCLES:
                enqueue_review(frame, suspected)
            elif suspected:
                logger.debug("[冷启动] 跳过%d个入队 (cycle=%d)", len(suspected), cycle_index)

        state["time"] = time.strftime("%H:%M:%S")
        state["counts"] = {
            "total": len(state["seats"]),
            "focus": sum(1 for e in state["events"] if e["risk"] == "高"),
            "normal": sum(1 for e in state["events"] if e["risk"] == "中"),
        }

        if cycle_index % _log_interval == 0:
            sc = {}
            for s in state["seats"]:
                sc[s["status"]] = sc.get(s["status"], 0) + 1
            logger.info("[周期#%d] 检测=%d(匹配%d/新增%d) 总座位=%d 状态=%s 事件=%d",
                        cycle_index, len(detections), matched_n, new_n,
                        len(state["seats"]), sc, len(state["events"]))

        cycle_index += 1
        time.sleep(0.1)

def frame_loader_worker():
    logger.info("[帧加载] 启动")
    idx = 0
    while True:
        state["frame"] = video_stream.get_latest_frame()
        idx += 1
        if idx % 500 == 0:
            logger.debug("[帧加载] 已读取 %d 帧", idx)
        time.sleep(0.04)
