import base64
import json
import logging
import os
import queue
import time
import cv2
import numpy as np
from collections import deque
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from scipy.optimize import linear_sum_assignment

from video_stream_util import MockMonitorStream

# 当前目录绝对路径
ROOT_PATH = Path(__file__).resolve().parent
# 事件截图输出
EVENT_CROP_DIR = ROOT_PATH / "outputs" / "event_crops"
# 创建输出目录（创建父级、存在不报错）
EVENT_CROP_DIR.mkdir(parents = True, exist_ok = True)

logger = logging.getLogger("monitor")

CLASS_VIDEOS = {
	"1班": ROOT_PATH / "inputs" / "test.mp4",
	"2班": ROOT_PATH / "inputs" / "v1.mp4",
	"3班": ROOT_PATH / "inputs" / "v2.mp4",
	"4班": ROOT_PATH / "inputs" / "v3.mp4"
}

DEFAULT_CLASS = "1班"

# 同一座位 VLM 送检间隔（秒）
VLM_INVOKE_SECONDS = 10
# 滑动窗口大小（最近几次检测结果）
WINDOW_SIZE = 5
# 睡觉出现次数 ≥ 此值 → 警告
DESK_LYING_WARN_COUNT = 2
# 低头+转头+吃东西 合计次数 ≥ 此值 → 提示
OTHER_ALERT_COUNT = 3
# 连续NORMAL次数 ≥ 此值 → 恢复
NORMAL_RECOVER_COUNT = 2

# 检测类别 → 状态码
CATEGORY_TO_STATUS = {
    0: "NORMAL",
    1: "HEAD_DOWN",
    2: "DESK_LYING",
    3: "TURNING_HEAD",
    4: "EATING",
}

# 异常状态
ABNORMAL_STATUSES = { "DESK_LYING", "HEAD_DOWN", "TURNING_HEAD", "EATING" }

# socket连接集合
websocket_clients = set()
# vlm待处理的任务队列
vlm_task_queue = queue.Queue(maxsize = 20)
# 座位最后送检时间记录，用来比对送检间隔
review_time_map = { }
# 当前队列中seat_id集合
vlm_pending = set()
# 每座最近检测类别滑动窗口 seat_id: deque(maxlen=WINDOW_SIZE)
detect_history = {}
# 每座连续NORMAL计数 seat_id: int
normal_streak = {}
# 每座当前告警等级 seat_id: "警告" | "提示" | None
alert_level_map = {}


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
		model_path = str(ROOT_PATH / "models" / "gmn26n-behavior.pt"),
		confidence_threshold = 0.25,
		image_size = 640,
	)
	logger.info("[Detect] 初始化完成")

	seat_id_counter = 1
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
		logger.info("[Detect] 模型检测耗时 %.2f", end - start)

		# 所有5个类别均参与
		detections = prediction.object_prediction_list
		seat_id_counter, _matched_n, _new_n = update_detected_seats(detections, seat_id_counter)

		# 根据检测类别更新座位状态并写入事件
		apply_detect_status(frame)

		state["time"] = time.strftime("%H:%M:%S")
		# 刷新前端统计卡片数据（按告警等级）
		state["counts"] = {
			"total": len(state["seats"]),
			"focus": sum(1 for v in alert_level_map.values() if v == "警告"),
			"normal": sum(1 for v in alert_level_map.values() if v == "提示"),
		}

		# 有异常才送VLM分析
		alert_seats = [s for s in state["seats"] if alert_level_map.get(s["seat_id"]) in ("警告", "提示")]
		enqueue_task(frame, alert_seats)
		time.sleep(2.0)


def frame_loader_worker():
	"""持续从当前视频源读取最新帧"""
	logger.info("[Video] 启动视频流")
	while True:
		state["frame"] = video_stream.get_latest_frame()
		time.sleep(0.04)


def update_detected_seats(detections, seat_id_counter):
	"""匈牙利算法实现座位匹配"""
	old_seats = state["seats"]
	detect_num = len(detections)
	seat_num = len(old_seats)

	# 没有检测框，清空所有座位
	if detect_num == 0:
		state["seats"] = []
		return seat_id_counter, 0, 0

	# 检测框坐标和类别
	detect_boxes = []
	detect_categories = []
	for detect in detections:
		raw_box = detect.bbox.to_xyxy()
		# 格式化sahi返回为盒子坐标 [x1, y1, x2, y2]
		box_xyxy = [round(raw_box[0], 2), round(raw_box[1], 2), round(raw_box[2], 2), round(raw_box[3], 2)]
		detect_boxes.append(box_xyxy)
		# 检测类别 0-4 正常、低头、睡觉、转头
		detect_categories.append(int(detect.category.id))

	# 没有座位，初始化
	if seat_num == 0:
		new_seats = []
		for i in range(detect_num):
			seat_id_counter += 1
			new_seats.append({
				"seat_id": seat_id_counter,
				"seat_code": f"S{seat_id_counter:02d}",
				"box": detect_boxes[i],
				"status": "NORMAL",
				"analysis_source": "",
				"locked_abnormal": False,
				"det_category": detect_categories[i],
			})
		state["seats"] = sorted(new_seats, key = lambda s: s["seat_id"])
		return seat_id_counter, 0, detect_num

	# 构建匈牙利算法成本矩阵
	# 行 = 检测框，列 = 已有座位 + 虚拟列（用于新建座位）
	# 虚拟列数 = 检测框数，确保每个检测框都有可行分配
	n_cols = seat_num + detect_num
	# 初始化为极大值，极大值为最高成本
	cost = np.full((detect_num, n_cols), 1e12, dtype = np.float64)

	for i in range(detect_num):
		# 当前检测框中心点
		detect_cx = (detect_boxes[i][0] + detect_boxes[i][2]) / 2.0
		detect_cy = (detect_boxes[i][1] + detect_boxes[i][3]) / 2.0
		# 检测框宽高
		box_w = detect_boxes[i][2] - detect_boxes[i][0]
		box_h = detect_boxes[i][3] - detect_boxes[i][1]
		# 匹配阈值为最长边的平方，超过此距离不匹配
		max_dist_sq = max(box_w, box_h) ** 2

		# 填充已有座位列：计算到每个已有座位的中心距离平方
		for j in range(seat_num):
			seat = old_seats[j]
			seat_cx = (seat["box"][0] + seat["box"][2]) / 2.0
			seat_cy = (seat["box"][1] + seat["box"][3]) / 2.0
			# 计算距离
			dist_sq = (detect_cx - seat_cx) ** 2 + (detect_cy - seat_cy) ** 2
			# 超过阈值则保持极大值，不匹配
			if dist_sq <= max_dist_sq:
				cost[i, j] = dist_sq

		# 填充虚拟列
		for j in range(seat_num, n_cols):
			cost[i, j] = max_dist_sq

	# scipy内置匈牙利算法求整体最优匹配
	row_ind, col_ind = linear_sum_assignment(cost)

	# 更新座位列表
	new_seats = []
	matched_n = 0
	new_n = 0

	for i, j in zip(row_ind, col_ind):
		if j < seat_num:
			# 匹配到进行更新
			seat = old_seats[j]
			# 浅拷贝防止变量污染
			seat = dict(seat)
			seat["box"] = detect_boxes[i]
			seat["det_category"] = detect_categories[i]
			new_seats.append(seat)
			matched_n += 1
		else:
			# 无匹配新列
			seat_id_counter += 1
			new_seats.append({
				"seat_id": seat_id_counter,
				"seat_code": f"S{seat_id_counter:02d}",
				"box": detect_boxes[i],
				"status": "NORMAL",
				"analysis_source": "",
				"locked_abnormal": False,
				"det_category": detect_categories[i],
			})
			new_n += 1

	# 按seat_id排序
	state["seats"] = sorted(new_seats, key = lambda s: s["seat_id"])
	return seat_id_counter, matched_n, new_n


def apply_detect_status(frame):
	"""滑动窗口判定事件写入条件"""
	for seat in state["seats"]:
		seat_id = seat["seat_id"]
		category = seat.get("det_category", 0)
		status = CATEGORY_TO_STATUS.get(category, "NORMAL")

		# 确保滑动窗口存在
		if seat_id not in detect_history:
			detect_history[seat_id] = deque(maxlen = WINDOW_SIZE)
		detect_history[seat_id].append(status)

		# 连续正常计数
		if status == "NORMAL":
			normal_streak[seat_id] = normal_streak.get(seat_id, 0) + 1
		else:
			normal_streak[seat_id] = 0

		# 连续次数突破阈值，恢复正常
		if normal_streak.get(seat_id, 0) >= NORMAL_RECOVER_COUNT:
			set_seat_status(seat, "NORMAL", "DETECT")
			alert_level_map.pop(seat_id, None)
			# 清除遗留数据
			detect_history[seat_id].clear()
			continue

		# 滑动窗口统计各类次数
		history = list(detect_history[seat_id])
		desk_count = history.count("DESK_LYING")
		# 低级异常合并计数
		other_count = sum(history.count(s) for s in ["HEAD_DOWN", "TURNING_HEAD", "EATING"])

		# 判定警告等级
		new_level = None
		if desk_count >= DESK_LYING_WARN_COUNT:
			new_level = "警告"
		elif other_count >= OTHER_ALERT_COUNT:
			new_level = "提示"

		old_level = alert_level_map.get(seat_id)

		# 状态未变只更新状态
		if new_level == old_level:
			set_seat_status(seat, status, "DETECT")
			continue

		# 状态变化进行更新
		if new_level is not None:
			alert_level_map[seat_id] = new_level
			set_seat_status(seat, status, "DETECT")
			append_event(
				{
					"status": status,
					"label": status,
					"reason": "",
					"level": new_level,
				},
				seat, frame, time.time_ns()
			)
		else:
			# 恢复为正常
			alert_level_map.pop(seat_id, None)
			set_seat_status(seat, status, "DETECT")


def reset_detection_state():
	"""重置检测数据"""
	review_time_map.clear()
	vlm_pending.clear()
	detect_history.clear()
	normal_streak.clear()
	alert_level_map.clear()
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
		# 服务停止后不处理
		if not state["is_running"]:
			set_vlm_pending(job["seats"], False)
			continue

		try:
			result = invoke_review(vlm, sys_content, job["frame"], job["seats"][0])
			handle_review_result(result, job["frame"])
		except Exception as exc:
			logger.error("[VLM-w%d] 分析异常: %s", worker_id, exc, exc_info = True)
		finally:
			set_vlm_pending(job["seats"], False)


def enqueue_task(frame, seats):
	"""任务入队列"""
	now = time.time()
	targets = []
	for seat in seats:
		seat_id = seat["seat_id"]
		# 已经处于待处理的不处理
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
	logger.info("[VLM] 模型分析耗时 %.2f", end - start)
	return response, seat, time.time_ns()


def apply_vlm_result(answer, frame, seat, ts_ms):
	"""VLM复核结果补充已有事件的 reason 和 label，不改变检测判定的告警等级"""
	current = None
	for s in state["seats"]:
		if s["seat_id"] == seat["seat_id"]:
			current = s
			break
	target = current or seat
	# 更新分析来源为VLM
	if current:
		current["analysis_source"] = "VLM"
	else:
		target["analysis_source"] = "VLM"

	if answer["status"] in ABNORMAL_STATUSES:
		# 找到该座位最近的事件，用VLM结果补充reason/label
		for ev in state["events"]:
			if ev["seat"] == target["seat_code"]:
				ev["reason"] = answer.get("reason", ev.get("reason", ""))
				ev["label"] = answer.get("label", ev.get("label", ""))
				ev["analysis_source"] = "VLM"
				ev["source"] = "VLM"
				break
		else:
			# 没有事件时回退创建（极少数情况）
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
			"level": answer.get("level", alert_level_map.get(target["seat_id"], "")),
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
	# 有告警等级即视为已锁定
	seat["locked_abnormal"] = alert_level_map.get(seat["seat_id"]) is not None


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
