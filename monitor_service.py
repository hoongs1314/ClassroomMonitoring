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

from video_stream_util import MockMonitorStream

# 当前目录绝对路径
ROOT_PATH = Path(__file__).resolve().parent
EVENT_CROP_DIR = ROOT_PATH / "outputs" / "event_crops"
EVENT_CROP_DIR.mkdir(parents = True, exist_ok = True)

logger = logging.getLogger("monitor")

CLASS_VIDEOS = {
	"1班": ROOT_PATH / "inputs" / "test.mp4",
	"2班": ROOT_PATH / "inputs" / "v1.mp4",
	"3班": ROOT_PATH / "inputs" / "v2.mp4",
	"4班": ROOT_PATH / "inputs" / "v3.mp4"
}

DEFAULT_CLASS = "1班"

# 同一座位 VLM 送检间隔
VLM_INVOKE_SECONDS = 15

# 异常状态
ABNORMAL_STATUSES = { "DESK_LYING", "HEAD_DOWN" }

# socket连接集合
websocket_clients = set()
# vlm待处理的任务队列
vlm_task_queue = queue.Queue(maxsize = 20)
# 座位最后送检时间记录，用来比对送检间隔
review_time_map = { }
# 当前队列中seat_id集合
vlm_pending = set()


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
	"""持续执行检测和 VLM 分析"""
	# sahi加载detect模型
	detector = AutoDetectionModel.from_pretrained(
		model_type = "ultralytics",
		model_path = str(ROOT_PATH / "models" / "detect.pt"),
		confidence_threshold = 0.25,
		image_size = 640,
	)
	logger.info("[Detect] 初始化完成")

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

		state["time"] = time.strftime("%H:%M:%S")
		# 刷新前端统计卡片数据
		state["counts"] = {
			"total": len(state["seats"]),
			"focus": sum(1 for event in state["events"] if event["status"] == "DESK_LYING"),
			"normal": sum(1 for event in state["events"] if event["status"] == "HEAD_DOWN"),
		}

		# 所有检测到的座位都参与 VLM 分析（受冷却时间限制）
		enqueue_task(frame, state["seats"])
		time.sleep(0.1)


def frame_loader_worker():
	"""持续从当前视频源读取最新帧"""
	logger.info("[Video] 启动视频流")
	while True:
		state["frame"] = video_stream.get_latest_frame()
		time.sleep(0.04)


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
				"analysis_source": "",
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
	review_time_map.clear()
	vlm_pending.clear()
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
		if not state["is_running"]:
			set_vlm_pending(job["seats"], False)
			continue

		try:
			result = invoke_review(vlm, sys_content, job["frame"], job["seats"][0])
			handle_review_result(result, job["frame"])
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
		if seat_id in vlm_pending:
			continue
		box = seat["box"]
		box_w = max(1, box[2] - box[0])
		box_h = max(1, box[3] - box[1])
		# 宽高比1:2的不送检
		if min(box_w, box_h) / max(box_w, box_h) <= 1.0 / 2.0:
			continue
		# 没到最小间隔的不处理
		cooldown_left = VLM_INVOKE_SECONDS - (now - review_time_map.get(seat_id, 0))
		if cooldown_left > 0:
			continue
		targets.append(dict(seat))

	frozen = frame.copy()
	for seat in targets:
		set_vlm_pending([seat], True)
		try:
			vlm_task_queue.put({ "frame": frozen, "seats": [seat] }, block = True, timeout = 3)
			review_time_map[seat["seat_id"]] = now
			logger.info("[VLM] 入队 %s", seat["seat_code"])
		except queue.Full:
			set_vlm_pending([seat], False)
			logger.warning("[VLM] 队列满，丢弃: %s", seat["seat_code"])


def handle_review_result(result, frame):
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
		logger.error("[VLM] 结果处理异常: %s %s", seat["seat_code"], exc, exc_info = True)
	return True


def invoke_review(vlm, sys_content, frame, seat):
	"""调用 VLM 分析裁剪图"""
	image = build_review_image(frame, seat)
	if image is None:
		return None

	img_b64 = encode_review_image(image)
	if not img_b64:
		logger.error("[VLM] 图片转换失败: %s", seat["seat_code"])
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
	logger.info("[VLM] 模型分析耗时 %.4f", end - start)
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
		set_seat_status(current, answer["status"], "VLM")
	else:
		target["analysis_source"] = "VLM"

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
			"source": target.get("analysis_source", "VLM"),
			"analysis_source": target.get("analysis_source", "VLM"),
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


def set_seat_status(seat, status, source = None):
	"""更新座位状态"""
	seat["status"] = status
	if source:
		seat["analysis_source"] = source
	seat["locked_abnormal"] = status in ABNORMAL_STATUSES


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
