import base64
import json
import logging
import os
import queue
import time
import cv2
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

from pose_engine import PoseEngine
from video_stream_util import MockMonitorStream

# 当前目录绝对路径
ROOT_PATH = Path(__file__).resolve().parent
EVENT_CROP_DIR = ROOT_PATH / "outputs" / "event_crops"
# 创建输出目录（创建父级、存在不报错）
EVENT_CROP_DIR.mkdir(parents = True, exist_ok = True)

logger = logging.getLogger("monitor")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
	_console_handler = logging.StreamHandler()
	_console_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S"))
	logger.addHandler(_console_handler)

CLASS_VIDEOS = {
	"1班": ROOT_PATH / "inputs" / "test.mp4",
	"2班": ROOT_PATH / "inputs" / "v1.mp4",
	"3班": ROOT_PATH / "inputs" / "v2.mp4",
	"4班": ROOT_PATH / "inputs" / "v3.mp4"
}

DEFAULT_CLASS = "1班"

# 疑似次数送检阈值
SUSPECT_CONFIRM_COUNT = 2
# 同一座位 VLM 送检间隔
VLM_INVOKE_SECONDS = 15
# 恢复正常次数阈值
RECOVER_CONFIRM_COUNT = 2
# 锁定最短时长
MIN_LOCK_TIMES = 15

# 什么时候开始送检（得等一会座位稳定）
VLM_START_TIME = 10
# 异常状态
ABNORMAL_STATUSES = { "DESK_LYING" }

# socket连接集合
websocket_clients = set()
# vlm待处理的任务队列
vlm_task_queue = queue.Queue(maxsize = 20)
# 座位最后送检时间记录，用来比对送检间隔
review_time_map = { }
# 当前队列中seat_id集合
vlm_pending = set()
# 疑似次数记录 seat_id: 次数
suspect_count_map = { }
# 正常次数记录 seat_id: 次数
recover_count_map = { }
# 锁定时间记录 seat_id: 锁定时间
locked_time_map = { }


def get_video_size(video_path):
	"""视频宽高"""
	cap = cv2.VideoCapture(str(video_path))
	w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
	h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
	cap.release()
	return w, h


# 当前激活视频的视频流
video_stream = MockMonitorStream(CLASS_VIDEOS[DEFAULT_CLASS])

IMG_W, IMG_H = get_video_size(CLASS_VIDEOS[DEFAULT_CLASS])

# 交互数据存储
state = {
	"is_running": False,
	"time": "00:00:00",
	"frame": video_stream.get_latest_frame(),
	"img_w": IMG_W,
	"img_h": IMG_H,
	"current_class": DEFAULT_CLASS,
	"class_list": list(CLASS_VIDEOS.keys()),
	"seats": [],
	"events": [],
	"counts": { "total": 0, "focus": 0, "normal": 0 },
}


def detection_analysis_loop():
	"""持续执行人体检测、姿态初筛和 VLM 复核入队"""
	# sahi加载detect模型
	detector = AutoDetectionModel.from_pretrained(
		model_type = "ultralytics",
		model_path = str(ROOT_PATH / "models" / "detect.pt"),
		confidence_threshold = 0.25,
		image_size = 640,
	)
	logger.info("[Detect] 初始化完成")

	pose_model = PoseEngine(str(ROOT_PATH / "models" / "gmn26n-pose-k9.pt"))
	logger.info("[Pose] 初始化完成")

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

		start = time.time()
		# sahi切片检测
		prediction = get_sliced_prediction(
			frame,
			detector,
			slice_height = 640,
			slice_width = 640,
			postprocess_match_threshold = 0.8
		)
		end = time.time()
		logger.info("[Detect] 模型检测耗时 %.4f", end - start)

		# 仅一类标签 0：person
		detections = [det for det in prediction.object_prediction_list if det.category.id == 0]
		seat_id_counter, _matched_n, _new_n = update_detected_seats(detections, seat_id_counter)

		apply_pose_status(frame, pose_model, cycle_index)
		state["time"] = time.strftime("%H:%M:%S")
		# 刷新前端统计卡片数据
		state["counts"] = {
			"total": len(state["seats"]),
			"focus": sum(1 for event in state["events"] if event["status"] == "DESK_LYING"),
			"normal": sum(1 for event in state["events"] if event["status"] == "HEAD_DOWN"),
		}

		cycle_index += 1
		time.sleep(0.1)


def frame_loader_worker():
	"""持续从当前视频源读取最新帧"""
	logger.info("[Video] 启动视频流")
	while True:
		state["frame"] = video_stream.get_latest_frame()
		time.sleep(0.04)


def apply_pose_status(frame, pose_model, cycle_index):
	"""按 Pose 结果更新座位状态并触发必要的 VLM 复核"""
	# 5次detect 1次pose
	if cycle_index % 5 != 0 or not state["seats"]:
		return

	suspected = []
	poses = pose_model.detect_poses_batch(frame, state["seats"])
	for index, (pose_status, _pose_conf, ratio, keypoint_conf) in enumerate(poses[:len(state["seats"])]):
		seat = state["seats"][index]

		if pose_status in ("SUSPECTED", "UNCERTAIN"):
			if pose_status == "SUSPECTED" and 0 < ratio < 0.03 and keypoint_conf > 0.45:
				set_seat_status(seat, "DESK_LYING")
				# 高置信直接采用标记异常，不用继续累计
				suspect_count_map[seat["seat_id"]] = 0
				logger.info("[Pose] 高置信异常: %s DESK_LYING", seat["seat_code"])
				continue
			if not seat.get("locked_abnormal"):
				set_seat_status(seat, pose_status)
			# 累计可疑次数
			suspect_count_map[seat["seat_id"]] = suspect_count_map.get(seat["seat_id"], 0) + 1
			recover_count_map[seat["seat_id"]] = 0
			# 次数超过阈值，锁定异常
			if suspect_count_map[seat["seat_id"]] >= SUSPECT_CONFIRM_COUNT:
				suspected.append(seat)
			continue

		# 异常积累清零
		suspect_count_map[seat["seat_id"]] = 0
		if not seat.get("locked_abnormal"):
			set_seat_status(seat, pose_status)
			continue

		# 锁定最短时间没到不能解锁
		lock_ts = locked_time_map.get(seat["seat_id"], 0)
		if time.time() - lock_ts < MIN_LOCK_TIMES:
			continue
		# 恢复分数累计
		recover_count_map[seat["seat_id"]] = recover_count_map.get(seat["seat_id"], 0) + 1
		# 恢复分数累计足够恢复正常状态
		if recover_count_map[seat["seat_id"]] >= RECOVER_CONFIRM_COUNT:
			set_seat_status(seat, pose_status)
			logger.info("[Pose] 解除锁定: %s", seat["seat_code"])

	# 座位可疑并且超过vlm间隔，再次送检
	if suspected and cycle_index >= VLM_START_TIME:
		enqueue_task(frame, suspected)


def update_detected_seats(detections, seat_id_counter):
	"""用本轮人体检测结果更新座位跟踪列表"""
	new_seats = []
	used_ids = set()
	matched_n = 0
	new_n = 0

	for det in detections:
		raw_box = det.bbox.to_xyxy()
		# 格式化sahi返回为盒子坐标
		box_xyxy = [round(raw_box[0], 2), round(raw_box[1], 2), round(raw_box[2], 2), round(raw_box[3], 2)]
		# 寻找座位最佳匹配
		best_match = find_matching_seat(box_xyxy, used_ids)

		if best_match:
			used_ids.add(best_match["seat_id"])
			best_match["box"] = box_xyxy
			new_seats.append(best_match)
			matched_n += 1
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

	state["seats"] = sorted(new_seats, key = lambda seat: seat["seat_id"])
	return seat_id_counter, matched_n, new_n


def find_matching_seat(box_xyxy, used_ids):
	"""使用中心点做最佳匹配"""
	best_match = None
	best_dist = float("inf")
	cur_x_avg = (box_xyxy[0] + box_xyxy[2]) / 2
	cur_y_avg = (box_xyxy[1] + box_xyxy[3]) / 2
	for seat in state["seats"]:
		if seat["seat_id"] in used_ids:
			continue
		sx_avg = (seat["box"][0] + seat["box"][2]) / 2
		sy_avg = (seat["box"][1] + seat["box"][3]) / 2
		dist = (cur_x_avg - sx_avg) ** 2 + (cur_y_avg - sy_avg) ** 2
		box_w = box_xyxy[2] - box_xyxy[0]
		box_h = box_xyxy[3] - box_xyxy[1]
		# 最长边
		threshold = max(box_w, box_h)
		# 偏移不能大于最长边
		if dist < threshold ** 2 and dist < best_dist:
			best_dist = dist
			best_match = seat
	return best_match


def reset_detection_state():
	"""重置检测数据"""
	suspect_count_map.clear()
	recover_count_map.clear()
	review_time_map.clear()
	vlm_pending.clear()
	locked_time_map.clear()
	# 清空队列
	while True:
		try:
			vlm_task_queue.get_nowait()
		except queue.Empty:
			break
	state["seats"] = []
	state["events"] = []
	state["counts"] = { "total": 0, "focus": 0, "normal": 0 }


def vlm_worker(worker_id):
	"""模型处理执行器"""
	api_key = os.environ.get("ALIYUN_API_KEY")
	if not api_key:
		logger.warning("[VLM-w%d] ALIYUN_API_KEY 未设置", worker_id)

	vlm = ChatOpenAI(
		model = "qwen-vl-max",
		api_key = api_key,
		base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1",
	)
	sys_content = (ROOT_PATH / "vlm_system_prompt.md").read_text(encoding = "utf-8")
	logger.info("[VLM] w%d 初始化", worker_id)

	while True:
		# 等任务,阻塞
		job = vlm_task_queue.get()
		# 停服了就不处理，释放 pending
		if not state["is_running"]:
			set_vlm_pending(job["seats"], False)
			continue

		try:
			result = invoke_review(vlm, sys_content, job["frame"], job["seats"][0], worker_id)
			handle_review_result(result, job["frame"], worker_id)
		except Exception as exc:
			logger.error("[VLM-w%d] 复核异常: %s", worker_id, exc, exc_info = True)
		finally:
			set_vlm_pending(job["seats"], False)


def enqueue_task(frame, seats):
	"""任务入队列"""
	now = time.time()
	targets = []
	for seat in seats:
		seat_id = seat["seat_id"]
		# 已经异常、已经处于待处理的不处理
		if seat.get("locked_abnormal") or seat_id in vlm_pending:
			continue
		# 没到最小间隔的不处理
		if now - review_time_map.get(seat_id, 0) < VLM_INVOKE_SECONDS:
			continue
		targets.append(dict(seat))

	frozen = frame.copy()
	# 逐座入队
	for seat in targets:
		set_vlm_pending([seat], True)
		try:
			vlm_task_queue.put({ "frame": frozen, "seats": [seat] }, block = True, timeout = 3)
			review_time_map[seat["seat_id"]] = now
			logger.info("[VLM] 入队 %s", seat["seat_code"])
		except queue.Full:
			# 满了丢一部分，防止一直堆积后面帧都处理不了
			set_vlm_pending([seat], False)
			logger.warning("[VLM] 队列满，丢弃: %s", seat["seat_code"])


def handle_review_result(result, frame, worker_id):
	"""处理 VLM 返回结果"""
	if result is None:
		return False
	response, seat, ts_ms = result
	if not state["is_running"]:
		return True

	try:
		answer = parse_model_json(response)
		apply_vlm_result(answer, frame, seat, ts_ms)
	except Exception as exc:
		logger.error("[VLM-w%d] 结果处理异常: %s %s", worker_id, seat["seat_code"], exc, exc_info = True)
	return True


def invoke_review(vlm, sys_content, frame, seat, worker_id):
	"""调用 VLM 分析裁剪图"""
	image = build_review_image(frame, seat)
	if image is None:
		return None

	img_b64 = encode_review_image(image)
	if not img_b64:
		logger.error("[VLM-w%d] 图片转换失败: %s", worker_id, seat["seat_code"])
		return None

	start = time.time()
	response = vlm.invoke(
		[
			SystemMessage(content = sys_content),
			HumanMessage(
				content = [
					{ "type": "image_url", "image_url": { "url": f"data:image/jpeg;base64,{img_b64}" } },
				]
			),
		]
	).content
	end = time.time()
	logger.info("[VLM] w%d 模型分析耗时 %.4f", worker_id, end - start)
	return response, seat, time.time_ns()


def apply_vlm_result(answer, frame, seat, ts_ms):
	"""应用 VLM 返回"""
	current = None
	for s in state["seats"]:
		if s["seat_id"] == seat["seat_id"]:
			current = s
			break
	target = current or seat
	if current:
		set_seat_status(current, answer["status"])

	if answer["status"] in ABNORMAL_STATUSES:
		append_event(answer, target, frame, ts_ms)
		logger.info("[VLM] 确认异常行为: %s %s", target["seat_code"], answer["status"])


def append_event(answer, target, frame, ts_ms):
	"""事件写入及本地持久化"""
	file_name = f"ev_{ts_ms}_{target['seat_code']}.jpg"
	x1, y1, x2, y2 = crop_bounds(frame, target["box"], 10)
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


def switch_class(class_name):
	"""切换班级、切换视频、重置数据"""
	video_path = CLASS_VIDEOS[class_name]
	video_stream.switch_video(video_path)
	state["current_class"] = class_name
	state["img_w"], state["img_h"] = get_video_size(video_path)
	state["frame"] = video_stream.get_latest_frame()
	reset_detection_state()
	logger.info("已切换班级到: %s", class_name)


def set_seat_status(seat, status):
	"""更新座位状态并更新异常锁定记录"""
	seat["status"] = status
	seat["locked_abnormal"] = status in ABNORMAL_STATUSES
	if seat["locked_abnormal"]:
		locked_time_map[seat["seat_id"]] = time.time()
	else:
		locked_time_map.pop(seat["seat_id"], None)


def set_vlm_pending(seats, enabled):
	"""设置座位的 VLM 处理状态"""
	for seat in seats:
		if enabled:
			vlm_pending.add(seat["seat_id"])
		else:
			vlm_pending.discard(seat["seat_id"])


def parse_model_json(response):
	"""解析 VLM 返回的 JSON"""
	content = response.strip()
	if content.startswith("```json"):
		content = content[len("```json"):]
	if content.endswith("```"):
		content = content[:-3]
	return json.loads(content.strip())


def crop_bounds(frame, box, pad):
	"""计算图像裁剪边界"""
	h, w = frame.shape[:2]
	return (
		max(0, int(box[0]) - pad),
		max(0, int(box[1]) - pad),
		min(w, int(box[2]) + pad),
		min(h, int(box[3]) + pad),
	)


def build_review_image(frame, seat):
	"""生成座位裁剪框"""
	x1, y1, x2, y2 = crop_bounds(frame, seat["box"], 10)
	# 固定顺序y轴、x轴
	crop = frame[y1:y2, x1:x2]
	if crop.size == 0:
		return None
	return crop


def encode_review_image(image):
	"""图片转成base64格式，质量80%"""
	ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
	return base64.b64encode(buf).decode("utf-8") if ok else ""
