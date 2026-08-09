import uvicorn
import asyncio
import logging
import threading
import time
import cv2

from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.bootstrap import bootstrap_admin_user
from core.config import settings
from core.database import SessionLocal, get_db, init_database
from core.dependencies import get_current_context, is_admin, load_context_from_token, parse_bearer_token
from domain.models import EduClass, EduTeacherClass, MonitorBehaviorEvent, MonitorSession
from services.monitor_service import (
	EVENT_CROP_DIR,
	detection_analysis_loop,
	frame_loader_worker,
	persist_state,
	refresh_runtime_class_config,
	recover_interrupted_sessions,
	vlm_worker,
	state,
	start_monitoring,
	stop_monitoring,
	switch_class,
	websocket_clients,
)
from services.schedule_service import schedule_worker_loop
from routers.auth_routes import router as auth_router
from routers.admin_routes import router as admin_router
from routers.teacher_routes import router as teacher_router
from routers.teaching_admin_routes import router as teaching_admin_router
from routers.course_analysis_routes import router as course_analysis_router
from routers.teacher_routes import _ensure_session_access

logger = logging.getLogger("monitor.service")
# Worker 数量由环境变量控制，避免在普通本机上无条件启动大量外部模型客户端。
VLM_WORKER_COUNT = settings.vlm_worker_count
# websocket通知间隔
BROADCAST_INTERVAL_SECONDS = 1.0
# 视频帧间隔
FRAME_INTERVAL_SECONDS = 0.04
# 已建立的媒体连接也必须定期重验登录状态与授权范围。
MEDIA_AUTH_RECHECK_SECONDS = 1.0

websocket_client_permissions = {}
websocket_client_tokens = {}


def decode_header_text(value):
	"""解码 URL 编码后的文本请求头，避免中文直接进入 HTTP Header。"""
	if value in (None, ""):
		return value
	return unquote(value)


def get_token_from_header_or_cookie(
	authorization = Header(default = None, alias = "Authorization"),
	media_token = Cookie(default = None, alias = "monitor_media_token"),
):
	"""媒体元素通过 HttpOnly Cookie 鉴权，避免把访问令牌暴露在 URL 中。"""
	if authorization:
		return parse_bearer_token(authorization)
	if media_token:
		return media_token
	raise HTTPException(status_code = 401, detail = "登录状态无效或已过期")


def get_current_context_from_header_or_query(
	db: Session = Depends(get_db),
	token = Depends(get_token_from_header_or_cookie),
):
	return load_context_from_token(db, token)


def get_runtime_access_context(token = Depends(get_token_from_header_or_cookie)):
	"""流式媒体在建立连接前完成鉴权，避免长期占用数据库连接。"""
	db = SessionLocal()
	try:
		context = load_context_from_token(db, token)
		return { "token": token, "allowed_classes": allowed_runtime_class_names(db, context) }
	finally:
		db.close()


def load_websocket_context(websocket, db):
	token = websocket.cookies.get("monitor_media_token")
	if not token:
		authorization = websocket.headers.get("authorization")
		if authorization:
			try:
				token = parse_bearer_token(authorization)
			except HTTPException:
				return None
	if not token:
		return None
	try:
		return load_context_from_token(db, token)
	except HTTPException:
		return None


def allowed_runtime_class_names(db, context, require_start = False):
	if is_admin(context):
		return None
	teacher = context.get("teacher")
	if not teacher:
		return set()
	permission_column = EduTeacherClass.can_start_monitor if require_start else EduTeacherClass.can_view_monitor
	today = datetime.now().date()
	rows = (
		db.query(EduClass.class_name)
		.join(EduTeacherClass, EduTeacherClass.class_id == EduClass.id)
		.filter(
			EduTeacherClass.teacher_id == teacher.id,
			EduTeacherClass.enabled == 1,
			permission_column == 1,
			or_(EduTeacherClass.start_date.is_(None), EduTeacherClass.start_date <= today),
			or_(EduTeacherClass.end_date.is_(None), EduTeacherClass.end_date >= today),
			EduClass.enabled == 1,
		)
		.all()
	)
	return {row[0] for row in rows}


def resolve_runtime_class_name(db, class_name = None, class_code = None):
	if class_code:
		row = db.query(EduClass.class_name).filter(EduClass.class_code == class_code, EduClass.enabled == 1).first()
		if not row:
			raise HTTPException(status_code = 400, detail = "班级编码无效或已停用")
		if class_name and class_name != row[0]:
			raise HTTPException(status_code = 400, detail = "班级名称与编码不一致")
		return row[0]
	if class_name:
		return class_name
	return state["current_class"]


def ensure_runtime_class_permission(db, context, class_name = None, class_code = None, require_start = False):
	target_class = resolve_runtime_class_name(db, class_name, class_code)
	if target_class not in state["class_list"]:
		raise HTTPException(status_code = 400, detail = "班级不存在或未配置实时视频源")
	allowed_classes = allowed_runtime_class_names(db, context, require_start)
	if allowed_classes is not None and target_class not in allowed_classes:
		action = "启动或切换" if require_start else "查看"
		raise HTTPException(status_code = 403, detail = f"无权{action}该班级监控")
	return target_class


def filter_status_payload(payload, allowed_classes):
	class_list = state["class_list"] if allowed_classes is None else [name for name in state["class_list"] if name in allowed_classes]
	if allowed_classes is None or payload["current_class"] in allowed_classes:
		return { **payload, "class_list": class_list }
	return {
		**payload,
		"is_running": False,
		"current_class": "",
		"class_list": class_list,
		"seats": [],
		"events": [],
		"counts": { "total": 0, "focus": 0, "normal": 0 },
	}


def build_status_payload():
	"""组装前端返回信息"""
	return {
		"is_running": state["is_running"],
		"time": state["time"],
		"img_w": state["img_w"],
		"img_h": state["img_h"],
		"current_class": state["current_class"],
		"class_list": state["class_list"],
		"seats": state["seats"],
		"events": state["events"],
		"counts": state["counts"],
		"phase": state.get("phase", "idle"),
		"error": state.get("error", ""),
	}


def start_background_threads():
	"""启动演示监控、课表调度和 VLM 线程。"""
	threading.Thread(target = frame_loader_worker, daemon = True).start()
	threading.Thread(target = detection_analysis_loop, daemon = True).start()
	threading.Thread(target = schedule_worker_loop, daemon = True).start()
	for worker_id in range(1, VLM_WORKER_COUNT + 1):
		threading.Thread(target = vlm_worker, args = (worker_id,), daemon = True).start()
	logger.info("[App] 后台线程已启动: 帧读取 + 检测 + 课表调度 + %d个VLM", VLM_WORKER_COUNT)


def refresh_websocket_permissions():
	"""每次推送前重验令牌与班级授权，权限变更立即对既有连接生效。"""
	permissions = {}
	invalid_clients = []
	db = SessionLocal()
	try:
		for client, token in tuple(websocket_client_tokens.items()):
			try:
				context = load_context_from_token(db, token)
				permissions[client] = allowed_runtime_class_names(db, context)
			except HTTPException:
				invalid_clients.append(client)
	except Exception as exc:
		logger.warning("[WS] 刷新客户端权限失败: %s", exc)
		permissions = { client: websocket_client_permissions.get(client) for client in websocket_clients }
	finally:
		db.close()
	return permissions, invalid_clients


async def broadcast_status_loop():
	"""定时发送帧数据"""
	while True:
		if websocket_clients:
			permissions, invalid_clients = refresh_websocket_permissions()
			for client in invalid_clients:
				with suppress(Exception):
					await client.close(code = 1008)
				websocket_clients.discard(client)
				websocket_client_permissions.pop(client, None)
				websocket_client_tokens.pop(client, None)
			payload = build_status_payload()
			clients = tuple(client for client in websocket_clients if client in permissions)
			results = await asyncio.gather(
				*(client.send_json(filter_status_payload(payload, permissions[client])) for client in clients),
				return_exceptions = True,
			)
			for client, result in zip(clients, results):
				if isinstance(result, Exception):
					websocket_clients.discard(client)
					websocket_client_permissions.pop(client, None)
					websocket_client_tokens.pop(client, None)
		await asyncio.sleep(BROADCAST_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""应用生命周期函数"""
	init_database()
	bootstrap_admin_user()
	recovered = recover_interrupted_sessions()
	if recovered:
		logger.warning("[App] 已将 %d 个无心跳的运行中课次标记为失败", recovered)
	refresh_runtime_class_config()
	start_background_threads()
	broadcast_task = asyncio.create_task(broadcast_status_loop())
	yield
	broadcast_task.cancel()
	with suppress(asyncio.CancelledError):
		await broadcast_task
	logger.info("[App] 服务关闭")


app = FastAPI(lifespan = lifespan)
# 请求中间件设置
app.add_middleware(
	CORSMiddleware,
	allow_origins = list(settings.cors_origins),
	allow_credentials = True,
	allow_methods = ["*"],
	allow_headers = ["*"],
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(teaching_admin_router)
app.include_router(teacher_router)
app.include_router(course_analysis_router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
	"""维持前端 WebSocket 连接并接收心跳消息"""
	db = SessionLocal()
	try:
		context = load_websocket_context(websocket, db)
		allowed_classes = allowed_runtime_class_names(db, context) if context else None
	finally:
		db.close()
	if not context:
		await websocket.close(code = 1008)
		return
	await websocket.accept()
	websocket_clients.add(websocket)
	websocket_client_permissions[websocket] = allowed_classes
	websocket_client_tokens[websocket] = context["token"]
	logger.info("[WS] 客户端连接: %d", len(websocket_clients))
	try:
		while True:
			await websocket.receive_text()
	except WebSocketDisconnect:
		websocket_clients.discard(websocket)
		websocket_client_permissions.pop(websocket, None)
		websocket_client_tokens.pop(websocket, None)
		logger.info("[WS] 客户端断开: %d", len(websocket_clients))
	except Exception as exc:
		websocket_clients.discard(websocket)
		websocket_client_permissions.pop(websocket, None)
		websocket_client_tokens.pop(websocket, None)
		logger.warning("[WS] 客户端异常断开: %s", exc)


def lastest_frames(token):
	"""持续输出当前监控帧，并在媒体连接存续期间重验权限。"""
	allowed_classes = set()
	next_auth_check = 0.0
	while True:
		if time.monotonic() >= next_auth_check:
			try:
				db = SessionLocal()
				try:
					context = load_context_from_token(db, token)
					allowed_classes = allowed_runtime_class_names(db, context)
				finally:
					db.close()
			except HTTPException:
				logger.info("[App] 视频流鉴权失效，主动结束连接")
				return
			except Exception as exc:
				logger.warning("[App] 视频流权限重验失败，主动结束连接: %s", exc)
				return
			next_auth_check = time.monotonic() + MEDIA_AUTH_RECHECK_SECONDS
		can_view_class = allowed_classes is None or state["current_class"] in allowed_classes
		if can_view_class and state["is_running"] and state["frame"] is not None:
			success, encoded_img = cv2.imencode(".jpg", state["frame"])
			if success:
				yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded_img.tobytes() + b"\r\n"
		time.sleep(FRAME_INTERVAL_SECONDS)


@app.get("/video_feed")
def video_feed_endpoint(
	runtime_access = Depends(get_runtime_access_context),
):
	"""视频流"""
	allowed_classes = runtime_access["allowed_classes"]
	if allowed_classes is not None and state["current_class"] not in allowed_classes:
		raise HTTPException(status_code = 403, detail = "无权查看该班级监控")
	logger.info("[App] 视频流客户端连接")
	return StreamingResponse(
		lastest_frames(runtime_access["token"]),
		media_type = "multipart/x-mixed-replace; boundary=frame",
		headers = { "Cache-Control": "no-store, private", "Pragma": "no-cache" },
	)


@app.get("/api/latest_frame")
def api_latest_frame(
	runtime_access = Depends(get_runtime_access_context),
):
	"""返回最新帧"""
	allowed_classes = runtime_access["allowed_classes"]
	if allowed_classes is not None and state["current_class"] not in allowed_classes:
		raise HTTPException(status_code = 403, detail = "无权查看该班级监控")
	if state["frame"] is None:
		return Response(status_code = 204, headers = { "Cache-Control": "no-store" })
	success, encoded_img = cv2.imencode(".jpg", state["frame"])
	if not success:
		return Response(status_code = 204, headers = { "Cache-Control": "no-store" })
	return Response(
		content = encoded_img.tobytes(), media_type = "image/jpeg",
		headers = { "Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0" }
		)


@app.get("/event_crops/{file_name}")
def event_crop_endpoint(
	file_name: str,
	context = Depends(get_current_context_from_header_or_query),
	db: Session = Depends(get_db),
):
	"""按事件所属课次校验权限后返回截图，避免公开暴露课堂图像。"""
	if Path(file_name).name != file_name:
		raise HTTPException(status_code = 404, detail = "截图不存在")
	image_url = f"/event_crops/{file_name}"
	event = db.query(MonitorBehaviorEvent).filter(MonitorBehaviorEvent.image_url == image_url).first()
	if not event:
		raise HTTPException(status_code = 404, detail = "截图不存在")
	_ensure_session_access(db, context, event.session_id)
	path = EVENT_CROP_DIR / file_name
	if not path.is_file():
		raise HTTPException(status_code = 404, detail = "截图文件不存在")
	return FileResponse(
		path,
		headers = { "Cache-Control": "no-store, private", "Pragma": "no-cache" },
	)


@app.post("/api/start")
def api_start_monitoring(
	x_class_name = Header(default = None, alias = "X-Class-Name"),
	x_class_code = Header(default = None, alias = "X-Class-Code"),
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	"""启动监控"""
	class_name = decode_header_text(x_class_name)
	target_class = ensure_runtime_class_permission(db, context, class_name, x_class_code, require_start = True)
	if state["is_running"]:
		raise HTTPException(status_code = 409, detail = "已有演示分析正在运行，请先结束当前课次")
	try:
		result = start_monitoring(
		class_name = target_class,
			operator_user_id = context["user"].id,
			operator_name = context["user"].real_name or context["user"].username,
		)
	except RuntimeError as exc:
		raise HTTPException(status_code = 409, detail = str(exc))
	logger.info("[App] 启动监控: %s", state["current_class"])
	return result


@app.post("/api/stop")
def api_stop_monitoring(
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	"""停止监控、清空状态"""
	if not is_admin(context):
		# 权限撤销不能让原操作人失去停止自己任务的能力，避免演示任务无人可停。
		if persist_state.get("session_id"):
			session = db.query(MonitorSession).filter(MonitorSession.id == persist_state["session_id"]).first()
			if not session or session.operator_user_id != context["user"].id:
				ensure_runtime_class_permission(db, context, require_start = True)
		else:
			ensure_runtime_class_permission(db, context, require_start = True)
	result = stop_monitoring()
	if not result.get("ok"):
		raise HTTPException(status_code = 500, detail = result.get("detail", "课后分析归档失败"))
	logger.info("[App] 停止监控")
	return result


@app.get("/api/classes")
def api_classes(
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	"""返回可切换班级列表和当前班级"""
	allowed_classes = allowed_runtime_class_names(db, context)
	class_list = state["class_list"] if allowed_classes is None else [name for name in state["class_list"] if name in allowed_classes]
	current = state["current_class"] if state["current_class"] in class_list else (class_list[0] if class_list else "")
	rows = db.query(EduClass.class_name, EduClass.class_code).filter(EduClass.class_name.in_(class_list), EduClass.enabled == 1).all() if class_list else []
	codes = { name: code for name, code in rows }
	return { "classes": [{ "class_name": name, "class_code": codes.get(name, "") } for name in class_list], "current": current }


@app.post("/api/switch_class")
async def api_switch_class(
	request: Request,
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	"""切换当前监控班级并重置检测状态"""
	body = await request.json()
	class_name = (body or { }).get("class", "")
	if class_name not in state["class_list"]:
		logger.warning("[App] 班级不存在: %s", class_name)
		return { "ok": False, "error": "班级不存在" }
	ensure_runtime_class_permission(db, context, class_name, require_start = True)
	if state["is_running"] and class_name != state["current_class"]:
		raise HTTPException(status_code = 409, detail = "演示分析运行中，不能切换班级")
	switch_class(class_name)
	logger.info("[App] 切换班级: %s", class_name)
	return { "ok": True, "current": state["current_class"] }


if __name__ == "__main__":
	"""启动 FastAPI 服务"""

	uvicorn.run(app, host = "0.0.0.0", port = 8997)
