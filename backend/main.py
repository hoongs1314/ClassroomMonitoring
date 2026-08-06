import uvicorn
import asyncio
import logging
import threading
import time
import cv2

from contextlib import asynccontextmanager, suppress
from urllib.parse import unquote
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from core.bootstrap import bootstrap_admin_user
from core.database import get_db, init_database
from core.dependencies import get_current_context, is_admin, load_context_from_token, parse_bearer_token
from domain.models import EduClass, EduTeacherClass
from services.monitor_service import (
	EVENT_CROP_DIR,
	detection_analysis_loop,
	frame_loader_worker,
	refresh_runtime_class_config,
	vlm_worker,
	state,
	start_monitoring,
	stop_monitoring,
	switch_class,
	websocket_clients,
)
from routers.auth_routes import router as auth_router
from routers.admin_routes import router as admin_router
from routers.teacher_routes import router as teacher_router

logger = logging.getLogger("monitor.service")
# Worker数量
VLM_WORKER_COUNT = 30
# websocket通知间隔
BROADCAST_INTERVAL_SECONDS = 1.0
# 视频帧间隔
FRAME_INTERVAL_SECONDS = 0.04

websocket_client_permissions = {}


def parse_optional_header_int(value, header_name):
	"""解析请求头中的整数参数，避免路径拼接 ID。"""
	if value in (None, ""):
		return None
	try:
		return int(value)
	except ValueError:
		logger.warning("[App] 请求头%s不是整数: %s", header_name, value)
		return None


def decode_header_text(value):
	"""解码 URL 编码后的文本请求头，避免中文直接进入 HTTP Header。"""
	if value in (None, ""):
		return value
	return unquote(value)


def get_token_from_header_or_query(
	authorization = Header(default = None, alias = "Authorization"),
	token = Query(default = None),
):
	"""视频流等浏览器原生请求无法设置 Header，允许使用 query token。"""
	if token:
		return token
	return parse_bearer_token(authorization)


def get_current_context_from_header_or_query(
	db: Session = Depends(get_db),
	token = Depends(get_token_from_header_or_query),
):
	return load_context_from_token(db, token)


def load_websocket_context(websocket, db):
	token = websocket.query_params.get("token")
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
	rows = (
		db.query(EduClass.class_name)
		.join(EduTeacherClass, EduTeacherClass.class_id == EduClass.id)
		.filter(
			EduTeacherClass.teacher_id == teacher.id,
			EduTeacherClass.enabled == 1,
			permission_column == 1,
			EduClass.enabled == 1,
		)
		.all()
	)
	return {row[0] for row in rows}


def resolve_runtime_class_name(db, class_name = None, class_code = None):
	if class_code:
		row = db.query(EduClass.class_name).filter(EduClass.class_code == class_code, EduClass.enabled == 1).first()
		if row:
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
	}


def start_background_threads():
	"""启动帧读取、检测分析和 VLM 线程"""
	threading.Thread(target = frame_loader_worker, daemon = True).start()
	threading.Thread(target = detection_analysis_loop, daemon = True).start()
	for worker_id in range(1, VLM_WORKER_COUNT + 1):
		threading.Thread(target = vlm_worker, args = (worker_id,), daemon = True).start()
	logger.info("[App] 后台线程已启动: 帧读取 + 检测 + %d个VLM", VLM_WORKER_COUNT)


async def broadcast_status_loop():
	"""定时发送帧数据"""
	while True:
		if websocket_clients:
			payload = build_status_payload()
			await asyncio.gather(
				*(client.send_json(filter_status_payload(payload, websocket_client_permissions.get(client))) for client in tuple(websocket_clients)),
				return_exceptions = True,
			)
		await asyncio.sleep(BROADCAST_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""应用生命周期函数"""
	init_database()
	bootstrap_admin_user()
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
	allow_origins = ["*"],
	allow_credentials = True,
	allow_methods = ["*"],
	allow_headers = ["*"],
)
app.mount("/event_crops", StaticFiles(directory = str(EVENT_CROP_DIR)), name = "event_crops")
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(teacher_router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
	"""维持前端 WebSocket 连接并接收心跳消息"""
	context = load_websocket_context(websocket, db)
	if not context:
		await websocket.close(code = 1008)
		return
	allowed_classes = allowed_runtime_class_names(db, context)
	await websocket.accept()
	websocket_clients.add(websocket)
	websocket_client_permissions[websocket] = allowed_classes
	logger.info("[WS] 客户端连接: %d", len(websocket_clients))
	try:
		while True:
			await websocket.receive_text()
	except WebSocketDisconnect:
		websocket_clients.discard(websocket)
		websocket_client_permissions.pop(websocket, None)
		logger.info("[WS] 客户端断开: %d", len(websocket_clients))
	except Exception as exc:
		websocket_clients.discard(websocket)
		websocket_client_permissions.pop(websocket, None)
		logger.warning("[WS] 客户端异常断开: %s", exc)


def lastest_frames(allowed_classes):
	"""持续输出当前监控帧"""
	while True:
		can_view_class = allowed_classes is None or state["current_class"] in allowed_classes
		if can_view_class and state["is_running"] and state["frame"] is not None:
			success, encoded_img = cv2.imencode(".jpg", state["frame"])
			if success:
				yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded_img.tobytes() + b"\r\n"
		time.sleep(FRAME_INTERVAL_SECONDS)


@app.get("/video_feed")
def video_feed_endpoint(
	context = Depends(get_current_context_from_header_or_query),
	db: Session = Depends(get_db),
):
	"""视频流"""
	allowed_classes = allowed_runtime_class_names(db, context)
	if allowed_classes is not None and state["current_class"] not in allowed_classes:
		raise HTTPException(status_code = 403, detail = "无权查看该班级监控")
	logger.info("[App] 视频流客户端连接")
	return StreamingResponse(lastest_frames(allowed_classes), media_type = "multipart/x-mixed-replace; boundary=frame")


@app.get("/api/latest_frame")
def api_latest_frame(
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	"""返回最新帧"""
	ensure_runtime_class_permission(db, context)
	if state["frame"] is None:
		return Response(status_code = 204, headers = { "Cache-Control": "no-store" })
	success, encoded_img = cv2.imencode(".jpg", state["frame"])
	if not success:
		return Response(status_code = 204, headers = { "Cache-Control": "no-store" })
	return Response(
		content = encoded_img.tobytes(), media_type = "image/jpeg",
		headers = { "Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0" }
		)


@app.post("/api/start")
def api_start_monitoring(
	x_class_name = Header(default = None, alias = "X-Class-Name"),
	x_class_code = Header(default = None, alias = "X-Class-Code"),
	x_teacher_id = Header(default = None, alias = "X-Teacher-Id"),
	x_operator_user_id = Header(default = None, alias = "X-Operator-User-Id"),
	x_operator_name = Header(default = None, alias = "X-Operator-Name"),
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	"""启动监控"""
	class_name = decode_header_text(x_class_name)
	ensure_runtime_class_permission(db, context, class_name, x_class_code, require_start = True)
	result = start_monitoring(
		class_name = class_name,
		class_code = x_class_code,
		teacher_id = parse_optional_header_int(x_teacher_id, "X-Teacher-Id"),
		operator_user_id = parse_optional_header_int(x_operator_user_id, "X-Operator-User-Id"),
		operator_name = decode_header_text(x_operator_name),
	)
	logger.info("[App] 启动监控: %s", state["current_class"])
	return result


@app.post("/api/stop")
def api_stop_monitoring(
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	"""停止监控、清空状态"""
	ensure_runtime_class_permission(db, context, require_start = True)
	result = stop_monitoring()
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
	return { "classes": class_list, "current": current }


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
	switch_class(class_name)
	logger.info("[App] 切换班级: %s", class_name)
	return { "ok": True, "current": state["current_class"] }


if __name__ == "__main__":
	"""启动 FastAPI 服务"""

	uvicorn.run(app, host = "0.0.0.0", port = 8997)
