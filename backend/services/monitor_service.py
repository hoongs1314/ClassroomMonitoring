import base64
import json
import logging
import os
import queue
import time
import cv2
import numpy as np
from collections import deque
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from scipy.optimize import linear_sum_assignment

from core.database import db_session
from core.paths import REPO_ROOT
from domain.models import (
	EduClass,
	EduTeacher,
	MonitorBehaviorEvent,
	MonitorEventFrame,
	MonitorSession,
	MonitorSessionSeat,
	MonitorVlmReview,
)
from services.video_stream_util import MockMonitorStream

# 当前目录绝对路径
ROOT_PATH = REPO_ROOT
PROMPT_PATH = ROOT_PATH / "backend" / "prompts" / "vlm_system_prompt.md"
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
CLASS_CODE_MAP = {
	"1班": "CLASS_1",
	"2班": "CLASS_2",
	"3班": "CLASS_3",
	"4班": "CLASS_4",
}
CLASS_NAME_BY_CODE = {code: name for name, code in CLASS_CODE_MAP.items()}
SUPPORTED_VIDEO_SUFFIXES = { ".mp4", ".avi", ".mov", ".mkv" }

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
persist_state = {
	"session_id": None,
	"class_id": None,
	"seat_db_ids": {},
	"event_db_ids": {},
}


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


def _resolve_video_path(video_path):
	path = Path(str(video_path or "").strip())
	return path if path.is_absolute() else ROOT_PATH / path


def list_video_sources():
	"""列出 inputs 目录中的可选本地测试视频，供管理员配置班级使用。"""
	input_dir = (ROOT_PATH / "inputs").resolve()
	if not input_dir.exists():
		return []
	return [
		{
			"path": path.relative_to(ROOT_PATH).as_posix(),
			"name": path.name,
		}
		for path in sorted(input_dir.iterdir(), key = lambda item: item.name.lower())
		if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_SUFFIXES
	]


def validate_video_source(video_path):
	"""校验班级视频仅引用项目 inputs 目录内已存在的本地测试文件。"""
	path = _resolve_video_path(video_path).resolve()
	input_dir = (ROOT_PATH / "inputs").resolve()
	try:
		path.relative_to(input_dir)
	except ValueError:
		raise ValueError("视频源路径必须位于 inputs 目录内")
	if path.suffix.lower() not in SUPPORTED_VIDEO_SUFFIXES:
		raise ValueError("视频源仅支持 mp4、avi、mov 或 mkv 文件")
	if not path.is_file():
		raise ValueError("视频源文件不存在")
	return path.relative_to(ROOT_PATH).as_posix()


def refresh_runtime_class_config():
	"""根据已启用班级刷新运行时视频源，管理端保存后立即生效。"""
	try:
		with db_session() as db:
			rows = db.query(EduClass).filter(EduClass.enabled == 1).order_by(EduClass.class_code.asc()).all()
			configs = [
				(row.class_name, row.class_code, validate_video_source(row.default_video_path))
				for row in rows
			]
	except Exception as exc:
		logger.warning("[Video] 刷新班级视频源失败: %s", exc)
		return False
	if not configs:
		logger.warning("[Video] 未找到可用班级视频源，保留当前配置")
		return False

	previous_video = CLASS_VIDEOS.get(state["current_class"])
	CLASS_VIDEOS.clear()
	CLASS_VIDEOS.update({ class_name: _resolve_video_path(video_path) for class_name, _, video_path in configs })
	CLASS_CODE_MAP.clear()
	CLASS_CODE_MAP.update({ class_name: class_code for class_name, class_code, _ in configs })
	CLASS_NAME_BY_CODE.clear()
	CLASS_NAME_BY_CODE.update({ class_code: class_name for class_name, class_code, _ in configs })
	state["class_list"] = list(CLASS_VIDEOS.keys())
	if state["is_running"]:
		return True
	if state["current_class"] not in CLASS_VIDEOS or previous_video != CLASS_VIDEOS[state["current_class"]]:
		switch_class(state["class_list"][0] if state["current_class"] not in CLASS_VIDEOS else state["current_class"])
	return True


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

		persist_seats()
		# 根据检测类别更新座位状态并写入事件
		apply_detect_status(frame)

		state["time"] = time.strftime("%H:%M:%S")
		# 刷新前端统计卡片数据（按告警等级）
		state["counts"] = {
			"total": len(state["seats"]),
			"focus": sum(1 for v in alert_level_map.values() if v == "警告"),
			"normal": sum(1 for v in alert_level_map.values() if v == "提示"),
		}
		update_session_counts()

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


def _ns_to_datetime(ts_ns):
	return datetime.fromtimestamp(ts_ns / 1_000_000_000)


def _build_session_no():
	return "MS%s%s" % (datetime.now().strftime("%Y%m%d%H%M%S"), uuid4().hex[:8])


def _safe_persist(action, description):
	try:
		return action()
	except Exception as exc:
		logger.warning("[Persist] %s失败: %s", description, exc)
		return None


def _resolve_class(db, class_name):
	class_code = CLASS_CODE_MAP.get(class_name)
	query = db.query(EduClass).filter(EduClass.enabled == 1)
	if class_code:
		row = query.filter(EduClass.class_code == class_code).first()
		if row:
			return row
	return query.filter(EduClass.class_name == class_name).first()


def _resolve_runtime_class(class_name = None, class_code = None):
	if class_code and class_code in CLASS_NAME_BY_CODE:
		return CLASS_NAME_BY_CODE[class_code]
	if class_name:
		return class_name
	return state["current_class"]


def start_monitoring(class_name = None, class_code = None, teacher_id = None, operator_user_id = None, operator_name = None):
	"""启动监控并尝试创建持久化会话；数据库异常不阻断实时监控。"""
	target_class = _resolve_runtime_class(class_name, class_code)
	if target_class != state["current_class"] and target_class in state["class_list"]:
		switch_class(target_class)
	state["is_running"] = True
	reset_detection_state()
	persist_state["session_id"] = None
	persist_state["class_id"] = None
	persist_state["seat_db_ids"] = {}
	persist_state["event_db_ids"] = {}

	def action():
		with db_session() as db:
			edu_class = _resolve_class(db, state["current_class"])
			if not edu_class:
				logger.warning("[Persist] 班级未入库，跳过会话持久化: %s", state["current_class"])
				return None
			teacher = db.query(EduTeacher).filter(EduTeacher.id == teacher_id).first() if teacher_id else None
			session = MonitorSession(
				session_no = _build_session_no(),
				class_id = edu_class.id,
				class_name = edu_class.class_name,
				teacher_id = teacher.id if teacher else None,
				teacher_name = teacher.teacher_name if teacher else None,
				operator_user_id = operator_user_id,
				operator_name = operator_name,
				video_path = str(CLASS_VIDEOS[state["current_class"]]),
				img_width = state["img_w"],
				img_height = state["img_h"],
				status = "RUNNING",
				started_at = datetime.utcnow(),
				last_heartbeat_at = datetime.utcnow(),
				rule_config_json = {
					"vlm_invoke_seconds": VLM_INVOKE_SECONDS,
					"window_size": WINDOW_SIZE,
					"desk_lying_warn_count": DESK_LYING_WARN_COUNT,
					"other_alert_count": OTHER_ALERT_COUNT,
					"normal_recover_count": NORMAL_RECOVER_COUNT,
				},
			)
			db.add(session)
			db.flush()
			persist_state["session_id"] = session.id
			persist_state["class_id"] = edu_class.id
			logger.info("[Persist] 监控会话已创建: %s", session.session_no)
			return session.id

	_safe_persist(action, "创建监控会话")
	return { "ok": True, "session_id": persist_state["session_id"] }


def stop_monitoring():
	"""停止监控并结束持久化会话。"""
	total_seat_count = len(persist_state["seat_db_ids"])
	warning_count = sum(1 for event in state["events"] if event.get("level") == "警告")
	notice_count = sum(1 for event in state["events"] if event.get("level") == "提示")
	event_count = len(state["events"])
	state["is_running"] = False
	state["seats"] = []
	state["events"] = []
	state["counts"] = { "total": 0, "focus": 0, "normal": 0 }
	session_id = persist_state.get("session_id")

	def action():
		if not session_id:
			return None
		with db_session() as db:
			session = db.query(MonitorSession).filter(MonitorSession.id == session_id).first()
			if session:
				session.status = "STOPPED"
				session.ended_at = datetime.utcnow()
				session.last_heartbeat_at = datetime.utcnow()
				session.total_seat_count = total_seat_count
				session.warning_count = warning_count
				session.notice_count = notice_count
				session.event_count = event_count

	_safe_persist(action, "结束监控会话")
	persist_state["session_id"] = None
	persist_state["class_id"] = None
	persist_state["seat_db_ids"] = {}
	persist_state["event_db_ids"] = {}
	return { "ok": True }


def persist_seats():
	session_id = persist_state.get("session_id")
	if not session_id:
		return

	def action():
		with db_session() as db:
			for seat in state["seats"]:
				box = seat["box"]
				row = (
					db.query(MonitorSessionSeat)
					.filter(
						MonitorSessionSeat.session_id == session_id,
						MonitorSessionSeat.runtime_seat_id == seat["seat_id"],
					)
					.first()
				)
				if not row:
					row = MonitorSessionSeat(
						session_id = session_id,
						runtime_seat_id = seat["seat_id"],
						seat_code = seat["seat_code"],
						box_x1 = box[0],
						box_y1 = box[1],
						box_x2 = box[2],
						box_y2 = box[3],
						first_seen_at = datetime.utcnow(),
					)
					db.add(row)
					db.flush()
				row.seat_code = seat["seat_code"]
				row.box_x1 = box[0]
				row.box_y1 = box[1]
				row.box_x2 = box[2]
				row.box_y2 = box[3]
				row.status = seat.get("status", "NORMAL")
				row.det_category = seat.get("det_category")
				row.analysis_source = seat.get("analysis_source")
				row.locked_abnormal = 1 if seat.get("locked_abnormal") else 0
				row.last_seen_at = datetime.utcnow()
				persist_state["seat_db_ids"][seat["seat_id"]] = row.id

	_safe_persist(action, "保存座位快照")


def update_session_counts():
	session_id = persist_state.get("session_id")
	if not session_id:
		return

	def action():
		with db_session() as db:
			session = db.query(MonitorSession).filter(MonitorSession.id == session_id).first()
			if not session:
				return
			session.last_heartbeat_at = datetime.utcnow()
			session.total_seat_count = state["counts"]["total"]
			session.warning_count = state["counts"]["focus"]
			session.notice_count = state["counts"]["normal"]
			session.event_count = len(state["events"])

	_safe_persist(action, "更新会话统计")


def persist_event(event_payload, target, file_name, ts_ns):
	session_id = persist_state.get("session_id")
	class_id = persist_state.get("class_id")
	if not session_id or not class_id:
		return

	def action():
		with db_session() as db:
			box = target["box"]
			seat_db_id = persist_state["seat_db_ids"].get(target["seat_id"])
			event = MonitorBehaviorEvent(
				event_uid = event_payload["event_id"],
				session_id = session_id,
				class_id = class_id,
				seat_id = seat_db_id,
				seat_code = target["seat_code"],
				level = event_payload.get("level", ""),
				status = event_payload.get("status", ""),
				label = event_payload.get("label", ""),
				reason = event_payload.get("reason", ""),
				source = event_payload.get("source", "DETECT"),
				analysis_source = event_payload.get("analysis_source", "DETECT"),
				image_url = event_payload.get("url"),
				image_path = str(EVENT_CROP_DIR / file_name),
				box_x1 = box[0],
				box_y1 = box[1],
				box_x2 = box[2],
				box_y2 = box[3],
				event_time = _ns_to_datetime(ts_ns),
				confirmed_by_vlm = 1 if event_payload.get("analysis_source") == "VLM" else 0,
			)
			db.add(event)
			db.flush()
			db.add(
				MonitorEventFrame(
					event_id = event.id,
					frame_index = 0,
					frame_time = event.event_time,
					focus_image_url = event.image_url,
					focus_image_path = event.image_path,
					seat_code = target["seat_code"],
					status = event.status,
					status_text = event.label,
					box_x1 = box[0],
					box_y1 = box[1],
					box_x2 = box[2],
					box_y2 = box[3],
					raw_payload_json = event_payload,
				)
			)
			persist_state["event_db_ids"][event_payload["event_id"]] = event.id

	_safe_persist(action, "保存异常事件")


def persist_vlm_result(event_payload, answer, raw_response, seat, ts_ns, latency_ms = None):
	session_id = persist_state.get("session_id")
	if not session_id:
		return
	event_uid = event_payload.get("event_id") if event_payload else None

	def action():
		with db_session() as db:
			event_id = persist_state["event_db_ids"].get(event_uid)
			event = db.query(MonitorBehaviorEvent).filter(MonitorBehaviorEvent.id == event_id).first() if event_id else None
			if event:
				event.reason = answer.get("reason", event.reason)
				event.label = answer.get("label", event.label)
				event.analysis_source = "VLM"
				event.source = "VLM"
				event.confirmed_by_vlm = 1
			db.add(
				MonitorVlmReview(
					event_id = event.id if event else None,
					session_id = session_id,
					seat_id = persist_state["seat_db_ids"].get(seat["seat_id"]),
					model_name = "qwen-vl-max",
					request_image_url = event_payload.get("url") if event_payload else None,
					request_image_path = str(EVENT_CROP_DIR / Path(event_payload.get("url", "")).name) if event_payload and event_payload.get("url") else None,
					raw_response = raw_response,
					parsed_status = answer.get("status"),
					parsed_label = answer.get("label"),
					parsed_reason = answer.get("reason"),
					success = 1,
					latency_ms = latency_ms,
					created_at = _ns_to_datetime(ts_ns),
				)
			)

	_safe_persist(action, "保存VLM复核")


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
	sys_content = PROMPT_PATH.read_text(encoding = "utf-8")
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
	response, seat, ts_ms, latency_ms = result
	if not state["is_running"]:
		return True

	try:
		answer = parse_model_json(response)
		apply_vlm_result(answer, frame, seat, ts_ms, response, latency_ms)
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
	return response, seat, time.time_ns(), int((end - start) * 1000)


def apply_vlm_result(answer, frame, seat, ts_ms, raw_response = "", latency_ms = None):
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
		event_payload = None
		for ev in state["events"]:
			if ev["seat"] == target["seat_code"]:
				ev["reason"] = answer.get("reason", ev.get("reason", ""))
				ev["label"] = answer.get("label", ev.get("label", ""))
				ev["analysis_source"] = "VLM"
				ev["source"] = "VLM"
				event_payload = ev
				break
		else:
			# 没有事件时回退创建（极少数情况）
			event_payload = append_event(answer, target, frame, ts_ms)
		persist_vlm_result(event_payload, answer, raw_response, target, ts_ms, latency_ms)
		logger.info("[VLM] 确认异常行为: %s %s", target["seat_code"], answer["status"])


def append_event(answer, target, frame, ts_ms):
	"""事件写入及本地持久化"""
	file_name = f"ev_{ts_ms}_{target['seat_code']}.jpg"
	event_uid = f"EV{ts_ms}_{target['seat_code']}"
	x1, y1, x2, y2 = crop_bounds(frame, target["box"], 10)
	cv2.imwrite(str(EVENT_CROP_DIR / file_name), frame[y1:y2, x1:x2])
	event_payload = {
		"id": time.time(),
		"event_id": event_uid,
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
	}
	state["events"].insert(
		0,
		event_payload,
	)
	persist_event(event_payload, target, file_name, ts_ms)
	return event_payload


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
