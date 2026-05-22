import base64
import json
import logging
import os
import queue
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

from pose_engine import PoseEngine
from video_stream_util import MockMonitorStream

ROOT_PATH = Path(__file__).resolve().parent
EVENT_CROP_DIR = ROOT_PATH / "outputs" / "event_crops"
EVENT_CROP_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("monitor")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
	_console_handler = logging.StreamHandler()
	_console_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S"))
	logger.addHandler(_console_handler)

CLASS_VIDEOS = {
	name: ROOT_PATH / "inputs" / file_name
	for name, file_name in {"1班": "test.mp4", "2班": "v1.mp4", "3班": "v2.mp4", "4班": "v3.mp4"}.items()
}
DEFAULT_CLASS = "1班"

SUSPECT_CONFIRM_COUNT = 2
REVIEW_COOLDOWN_SECONDS = 10
REVIEW_CROP_PAD = 8
EVENT_CROP_PAD = 20
RECOVER_CONFIRM_COUNT = 2
MIN_LOCK_SECONDS = 15
VLM_BATCH_MAX = 6
VLM_THREAD_POOL_MAX = 6
COLD_START_CYCLES = 8
ABNORMAL_STATUSES = {"HEAD_DOWN", "DESK_LYING"}

websocket_clients = set()
review_queue = queue.Queue(maxsize=12)
review_last_at = {}
review_pending = set()
suspect_hits = {}
recover_hits = {}
locked_at = {}
vlm_review_executor = ThreadPoolExecutor(max_workers=VLM_THREAD_POOL_MAX, thread_name_prefix="vlm-review")


def get_video_dims(video_path):
	"""读取视频文件的宽高。"""
	cap = cv2.VideoCapture(str(video_path))
	w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
	h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
	cap.release()
	return w, h


video_stream = MockMonitorStream(CLASS_VIDEOS[DEFAULT_CLASS])
initial_frame = video_stream.get_latest_frame()
IMG_W, IMG_H = get_video_dims(CLASS_VIDEOS[DEFAULT_CLASS])

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

logger.info("监控服务初始化完成: %s %dx%d", DEFAULT_CLASS, IMG_W, IMG_H)


def reset_detection_state():
	"""清空检测缓存、复核队列和前端展示状态。"""
	for container in (suspect_hits, recover_hits, review_last_at, review_pending, locked_at):
		container.clear()
	while True:
		try:
			review_queue.get_nowait()
		except queue.Empty:
			break
	state["seats"] = []
	state["events"] = []
	state["counts"] = {"total": 0, "focus": 0, "normal": 0}


def switch_class(class_name):
	"""切换班级视频源并重置检测状态。"""
	video_path = CLASS_VIDEOS[class_name]
	video_stream.switch_video(video_path)
	state["current_class"] = class_name
	state["img_w"], state["img_h"] = get_video_dims(video_path)
	state["frame"] = video_stream.get_latest_frame()
	reset_detection_state()
	logger.info("已切换班级: %s", class_name)
	return True


def box_center(box):
	"""计算检测框中心点坐标。"""
	return (box[2] + box[0]) / 2, (box[3] + box[1]) / 2


def box_distance_sq(box_a, box_b):
	"""计算两个检测框中心点的平方距离。"""
	ax, ay = box_center(box_a)
	bx, by = box_center(box_b)
	return (ax - bx) ** 2 + (ay - by) ** 2


def box_iou(box_a, box_b):
	"""计算两个检测框的 IoU。"""
	x1 = max(box_a[0], box_b[0])
	y1 = max(box_a[1], box_b[1])
	x2 = min(box_a[2], box_b[2])
	y2 = min(box_a[3], box_b[3])
	inter = max(0, x2 - x1) * max(0, y2 - y1)
	area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
	area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
	union = area_a + area_b - inter
	return inter / union if union > 0 else 0


def crop_bounds(frame, box, pad):
	"""按检测框和外扩像素计算图像内裁剪边界。"""
	h, w = frame.shape[:2]
	return (
		max(0, int(box[0]) - pad),
		max(0, int(box[1]) - pad),
		min(w, int(box[2]) + pad),
		min(h, int(box[3]) + pad),
	)


def build_review_image(frame, seat):
	"""生成单个座位送 VLM 复核的裁剪图片。"""
	x1, y1, x2, y2 = crop_bounds(frame, seat["box"], REVIEW_CROP_PAD)
	crop = frame[y1:y2, x1:x2]
	if crop.size == 0:
		return None
	return crop


def encode_review_image(image):
	"""把复核图片编码成 VLM 可接收的 base64 JPEG。"""
	ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
	return base64.b64encode(buf).decode("utf-8") if ok else ""


def invoke_single_review(vlm, sys_content, frame, seat, worker_id):
	"""调用 VLM 对单个座位裁剪图进行复核。"""
	image = build_review_image(frame, seat)
	if image is None:
		return None

	img_b64 = encode_review_image(image)
	if not img_b64:
		logger.error("[VLM-w%d] 图片编码失败: %s", worker_id, seat["seat_code"])
		return None

	response = vlm.invoke(
		[
			SystemMessage(content=sys_content),
			HumanMessage(
				content=[
					{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
				]
			),
		]
	).content
	return response, seat, time.time_ns()


def set_seat_status(seat, status):
	"""更新座位状态并维护异常锁定时间。"""
	seat["status"] = status
	seat["locked_abnormal"] = status in ABNORMAL_STATUSES
	if seat["locked_abnormal"]:
		locked_at[seat["seat_id"]] = time.time()
	else:
		locked_at.pop(seat["seat_id"], None)


def parse_model_json(response):
	"""解析 VLM 返回的姿态 JSON 对象。"""
	content = response.strip()
	if content.startswith("```json"):
		content = content[len("```json"):]
	if content.endswith("```"):
		content = content[:-3]
	return json.loads(content.strip())


def append_event(answer, target, frame, ts_ms, raw_response):
	"""把确认异常写入前端事件列表并保存事件截图。"""
	file_name = f"ev_{ts_ms}_{target['seat_code']}.jpg"
	x1, y1, x2, y2 = crop_bounds(frame, target["box"], EVENT_CROP_PAD)
	cv2.imwrite(str(EVENT_CROP_DIR / file_name), frame[y1:y2, x1:x2])
	state["events"].insert(
		0,
		{
			"id": time.time(),
			"time": time.strftime("%H:%M:%S"),
			"seat": target["seat_code"],
			"status": answer["status"],
			"label": answer["label"],
			"reason": answer["reason"],
			"url": f"/event_crops/{file_name}",
			"box": target["box"],
		},
	)


def apply_review_result(response, answer, frame, seat, ts_ms):
	"""把 VLM 复核结果应用到当前座位状态和事件列表。"""
	current = next((s for s in state["seats"] if s["seat_id"] == seat["seat_id"]), None)
	target = current or seat
	if current:
		set_seat_status(current, answer["status"])

	if answer["status"] in ABNORMAL_STATUSES:
		append_event(answer, target, frame, ts_ms, response)
		logger.info("[VLM结果] 异常确认: %s %s", target["seat_code"], answer["status"])


def set_review_pending(seats, enabled):
	"""设置一组座位的 VLM 复核占用状态。"""
	action = review_pending.add if enabled else review_pending.discard
	for seat in seats:
		action(seat["seat_id"])


def handle_review_future(future, frame, worker_id):
	"""处理单个 VLM future 的返回结果。"""
	try:
		result = future.result()
	except Exception as exc:
		logger.error("[VLM-w%d] 单图复核异常: %s", worker_id, exc, exc_info=True)
		return False

	if result is None:
		return False
	response, seat, ts_ms = result
	if not state["is_running"]:
		return True

	try:
		answer = parse_model_json(response)
		apply_review_result(response, answer, frame, seat, ts_ms)
	except Exception as exc:
		logger.error("[VLM-w%d] 结果处理异常: %s %s", worker_id, seat["seat_code"], exc, exc_info=True)
	return True


def enqueue_review(frame, seats):
	"""把需要 VLM 复核的座位按批次加入队列。"""
	now = time.time()
	targets = []
	for seat in seats:
		seat_id = seat["seat_id"]
		if seat.get("locked_abnormal") or seat_id in review_pending:
			continue
		if now - review_last_at.get(seat_id, 0) < REVIEW_COOLDOWN_SECONDS:
			continue
		targets.append(dict(seat))

	# 队列保存帧副本，避免后续帧刷新影响 VLM 输入。
	for start in range(0, len(targets), VLM_BATCH_MAX):
		batch = targets[start:start + VLM_BATCH_MAX]
		set_review_pending(batch, True)
		try:
			review_queue.put({"frame": frame.copy(), "seats": batch}, block=True, timeout=3)
			review_last_at.update((seat["seat_id"], now) for seat in batch)
			logger.info("[VLM入队] %d个座位", len(batch))
		except queue.Full:
			set_review_pending(batch, False)
			logger.warning("[VLM入队] 队列满，丢弃%d个座位", len(batch))


def make_vlm_worker(worker_id):
	"""创建一个持续消费复核队列的 VLM worker。"""

	def run():
		"""运行单个 VLM worker 的复核循环。"""
		api_key = os.environ.get("ALIYUN_API_KEY")
		if not api_key:
			logger.warning("[VLM-w%d] ALIYUN_API_KEY 未设置", worker_id)

		vlm = ChatOpenAI(
			model="qwen-vl-max",
			api_key=api_key,
			base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
		)
		sys_content = (ROOT_PATH / "vlm_system_prompt.md").read_text(encoding="utf-8")
		logger.info("[VLM-w%d] 就绪", worker_id)

		while True:
			job = review_queue.get()
			if not state["is_running"]:
				set_review_pending(job["seats"], False)
				continue

			try:
				futures = [
					vlm_review_executor.submit(invoke_single_review, vlm, sys_content, job["frame"], seat, worker_id)
					for seat in job["seats"]
				]
				for future in as_completed(futures):
					handle_review_future(future, job["frame"], worker_id)
			except Exception as exc:
				logger.error("[VLM-w%d] 批量复核异常: %s", worker_id, exc, exc_info=True)
			finally:
				set_review_pending(job["seats"], False)

	return run


def create_detector():
	"""加载 SAHI 人体检测模型。"""
	return AutoDetectionModel.from_pretrained(
		model_type="ultralytics",
		model_path=str(ROOT_PATH / "models" / "detect.pt"),
		confidence_threshold=0.25,
	)


def detection_box(det):
	"""从 SAHI 检测结果提取 xyxy 坐标。"""
	raw_box = det.bbox.to_xyxy()
	return [round(raw_box[0], 2), round(raw_box[1], 2), round(raw_box[2], 2), round(raw_box[3], 2)]


def find_matching_seat(box_xyxy, used_ids):
	"""在当前座位列表中按 IoU 和中心距离匹配检测框。"""
	best_match = None
	best_iou = 0
	for seat in state["seats"]:
		if seat["seat_id"] in used_ids:
			continue
		iou = box_iou(box_xyxy, seat["box"])
		if iou > 0.3 or box_distance_sq(box_xyxy, seat["box"]) < 5000:
			if iou > best_iou:
				best_iou = iou
				best_match = seat
	return best_match


def update_detected_seats(detections, seat_id_counter):
	"""用本轮人体检测结果更新座位跟踪列表。"""
	new_seats = []
	used_ids = set()
	matched_n = 0
	new_n = 0

	for det in detections:
		box_xyxy = detection_box(det)
		best_match = find_matching_seat(box_xyxy, used_ids)

		if best_match:
			used_ids.add(best_match["seat_id"])
			best_match["box"] = box_xyxy
			new_seats.append(best_match)
			matched_n += 1
			continue

		# 新座位只在与本轮新增框不重叠时创建。
		if any(box_iou(box_xyxy, seat["box"]) > 0.5 for seat in new_seats):
			continue
		seat_id_counter += 1
		new_seats.append(
			{
				"seat_id": seat_id_counter,
				"seat_code": f"S{seat_id_counter - 100:02d}",
				"box": box_xyxy,
				"status": "NORMAL",
				"locked_abnormal": False,
			}
		)
		new_n += 1

	state["seats"] = sorted(new_seats, key=lambda seat: seat["seat_id"])
	return seat_id_counter, matched_n, new_n


def apply_pose_status(frame, pose_model, cycle_index):
	"""按 Pose 初筛结果更新座位状态并触发必要的 VLM 复核。"""
	if cycle_index % 3 != 0 or not state["seats"]:
		return

	suspected = []
	poses = pose_model.detect_poses_batch(frame, state["seats"])
	for index, (pose_status, _pose_conf, ratio, keypoint_conf) in enumerate(poses[:len(state["seats"])]):
		seat = state["seats"][index]

		if pose_status in ("SUSPECTED", "UNCERTAIN"):
			# 高置信低头直接锁定，模糊状态累积后交给 VLM。
			if pose_status == "SUSPECTED" and ratio < 0.03 and keypoint_conf > 0.55:
				set_seat_status(seat, "HEAD_DOWN")
				suspect_hits[seat["seat_id"]] = 0
				logger.info("[Pose] 高置信异常: %s HEAD_DOWN", seat["seat_code"])
				continue
			if not seat.get("locked_abnormal"):
				set_seat_status(seat, pose_status)
			suspect_hits[seat["seat_id"]] = suspect_hits.get(seat["seat_id"], 0) + 1
			recover_hits[seat["seat_id"]] = 0
			if suspect_hits[seat["seat_id"]] >= SUSPECT_CONFIRM_COUNT:
				suspected.append(seat)
			continue

		suspect_hits[seat["seat_id"]] = 0
		if not seat.get("locked_abnormal"):
			set_seat_status(seat, pose_status)
			continue

		lock_ts = locked_at.get(seat["seat_id"], 0)
		if time.time() - lock_ts < MIN_LOCK_SECONDS:
			continue
		recover_hits[seat["seat_id"]] = recover_hits.get(seat["seat_id"], 0) + 1
		if recover_hits[seat["seat_id"]] >= RECOVER_CONFIRM_COUNT:
			set_seat_status(seat, pose_status)
			logger.info("[恢复] 解除锁定: %s", seat["seat_code"])

	if suspected and cycle_index >= COLD_START_CYCLES:
		enqueue_review(frame, suspected)


def update_counts():
	"""刷新前端统计卡片数据。"""
	state["counts"] = {
		"total": len(state["seats"]),
		"focus": sum(1 for event in state["events"] if event["status"] == "DESK_LYING"),
		"normal": sum(1 for event in state["events"] if event["status"] == "HEAD_DOWN"),
	}


def detection_analysis_loop():
	"""持续执行人体检测、姿态初筛和 VLM 复核入队。"""
	logger.info("[检测引擎] 初始化模型")
	detector = create_detector()
	pose_model = PoseEngine(str(ROOT_PATH / "models" / "yolo26s-pose.pt"))
	logger.info("[检测引擎] 模型加载完成")

	cycle_index = 0
	seat_id_counter = 100
	while True:
		if not state["is_running"]:
			time.sleep(0.5)
			continue

		frame = state["frame"]
		if frame is None:
			time.sleep(0.05)
			continue

		prediction = get_sliced_prediction(frame, detector, slice_height=640, slice_width=640, verbose=0)
		detections = [det for det in prediction.object_prediction_list if det.category.id == 0]
		seat_id_counter, _matched_n, _new_n = update_detected_seats(detections, seat_id_counter)
		apply_pose_status(frame, pose_model, cycle_index)
		state["time"] = time.strftime("%H:%M:%S")
		update_counts()

		cycle_index += 1
		time.sleep(0.1)


def frame_loader_worker():
	"""持续从当前视频源读取最新帧。"""
	logger.info("[帧加载] 启动")
	while True:
		state["frame"] = video_stream.get_latest_frame()
		time.sleep(0.04)
