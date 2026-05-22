import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager, suppress

import cv2
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from monitor_service import (
	EVENT_CROP_DIR,
	detection_analysis_loop,
	frame_loader_worker,
	make_vlm_worker,
	state,
	switch_class,
	websocket_clients,
)

logger = logging.getLogger("monitor.service")
VLM_WORKER_COUNT = 3
BROADCAST_INTERVAL_SECONDS = 1.0
FRAME_INTERVAL_SECONDS = 0.04


def build_status_payload():
	"""生成前端 WebSocket 使用的实时状态快照。"""
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
	"""启动帧读取、检测分析和 VLM 复核后台线程。"""
	threading.Thread(target=frame_loader_worker, daemon=True).start()
	threading.Thread(target=detection_analysis_loop, daemon=True).start()
	for worker_id in range(1, VLM_WORKER_COUNT + 1):
		threading.Thread(target=make_vlm_worker(worker_id), daemon=True).start()
	logger.info("后台线程已启动: 帧读取 + 检测 + %d个VLM", VLM_WORKER_COUNT)


async def broadcast_status_loop():
	"""定时向所有 WebSocket 客户端广播监控状态。"""
	while True:
		if websocket_clients:
			payload = build_status_payload()
			await asyncio.gather(
				*(client.send_json(payload) for client in tuple(websocket_clients)),
				return_exceptions=True,
			)
		await asyncio.sleep(BROADCAST_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""管理服务生命周期内的后台线程和广播任务。"""
	start_background_threads()
	broadcast_task = asyncio.create_task(broadcast_status_loop())
	yield
	broadcast_task.cancel()
	with suppress(asyncio.CancelledError):
		await broadcast_task
	logger.info("服务关闭")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
app.mount("/event_crops", StaticFiles(directory=str(EVENT_CROP_DIR)), name="event_crops")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
	"""维持前端 WebSocket 连接并接收心跳消息。"""
	await websocket.accept()
	websocket_clients.add(websocket)
	logger.info("[WS] 客户端连接: %d", len(websocket_clients))
	try:
		while True:
			await websocket.receive_text()
	except WebSocketDisconnect:
		websocket_clients.discard(websocket)
		logger.info("[WS] 客户端断开: %d", len(websocket_clients))
	except Exception as exc:
		websocket_clients.discard(websocket)
		logger.warning("[WS] 客户端异常断开: %s", exc)


def iter_mjpeg_frames():
	"""持续输出当前监控帧的 MJPEG 数据块。"""
	while True:
		if state["is_running"] and state["frame"] is not None:
			success, encoded_img = cv2.imencode(".jpg", state["frame"])
			if success:
				yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded_img.tobytes() + b"\r\n"
		time.sleep(FRAME_INTERVAL_SECONDS)


@app.get("/video_feed")
def video_feed_endpoint():
	"""提供前端主画面使用的 MJPEG 视频流。"""
	logger.info("[MJPEG] 视频流客户端连接")
	return StreamingResponse(iter_mjpeg_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/latest_frame")
def api_latest_frame():
	"""返回当前最新帧的 JPEG 图片。"""
	if state["frame"] is None:
		return Response(status_code=204)
	success, encoded_img = cv2.imencode(".jpg", state["frame"])
	if not success:
		return Response(status_code=204)
	return Response(content=encoded_img.tobytes(), media_type="image/jpeg")


@app.post("/api/start")
def api_start_monitoring():
	"""启动课堂监控状态。"""
	state["is_running"] = True
	logger.info("[API] 启动监控: %s", state["current_class"])
	return {"ok": True}


@app.post("/api/stop")
def api_stop_monitoring():
	"""停止课堂监控并清空当前展示状态。"""
	state["is_running"] = False
	state["seats"] = []
	state["events"] = []
	state["counts"] = {"total": 0, "focus": 0, "normal": 0}
	logger.info("[API] 停止监控")
	return {"ok": True}


@app.get("/api/classes")
def api_classes():
	"""返回可切换班级列表和当前班级。"""
	return {"classes": state["class_list"], "current": state["current_class"]}


@app.post("/api/switch_class")
async def api_switch_class(request: Request):
	"""切换当前监控班级并重置检测状态。"""
	body = await request.json()
	class_name = (body or {}).get("class", "")
	if class_name not in state["class_list"]:
		logger.warning("[API] 班级不存在: %s", class_name)
		return {"ok": False, "error": "班级不存在"}
	switch_class(class_name)
	logger.info("[API] 切换班级: %s", class_name)
	return {"ok": True, "current": state["current_class"]}


if __name__ == "__main__":
	"""以脚本方式启动本地 FastAPI 服务。"""
	import uvicorn

	uvicorn.run(app, host="0.0.0.0", port=8997)
