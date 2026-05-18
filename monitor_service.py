import json
import logging
import asyncio
import threading
import cv2
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from monitor_impl import state, websocket_clients, frame_loader_worker, detection_analysis_loop, make_vlm_worker, EVENT_CROP_DIR, switch_class

logger = logging.getLogger("monitor.service")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("启动工作线程...")
    threading.Thread(
        target=frame_loader_worker,
        daemon=True
    ).start()

    threading.Thread(
        target=detection_analysis_loop,
        daemon=True
    ).start()

    for w in range(3):
        threading.Thread(target=make_vlm_worker(w + 1), daemon=True).start()
    logger.info("5个工作线程已启动 (帧+检测+3×VLM)")

    async def status_broadcast_loop():
        _bc_idx = 0
        while True:
            if websocket_clients:
                payload_dict = {
                    "is_running": state["is_running"],
                    "time": state["time"],
                    "img_w": state["img_w"],
                    "img_h": state["img_h"],
                    "current_class": state["current_class"],
                    "class_list": state["class_list"],
                    "seats": state["seats"],
                    "events": state["events"],
                    "counts": state["counts"]
                }

                payload_json = json.dumps(payload_dict)

                await asyncio.gather(
                    *[client.send_text(payload_json) for client in websocket_clients],
                    return_exceptions=True
                )
            _bc_idx += 1
            if _bc_idx % 60 == 0:
                logger.debug(
                    "[广播] clients=%d seats=%d events=%d class=%s",
                    len(websocket_clients), len(state["seats"]),
                    len(state["events"]), state["current_class"]
                )
            await asyncio.sleep(1)

    broadcast_task = asyncio.create_task(status_broadcast_loop())

    yield

    broadcast_task.cancel()
    logger.info("服务关闭")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.mount(
    "/event_crops",
    StaticFiles(directory=str(EVENT_CROP_DIR))
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_clients.add(websocket)
    logger.info("[WS] 客户端连接 (当前%d个)", len(websocket_clients))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)
        logger.info("[WS] 客户端断开 (剩余%d个)", len(websocket_clients))
    except:
        websocket_clients.remove(websocket)
        logger.info("[WS] 客户端异常断开 (剩余%d个)", len(websocket_clients))

@app.get("/video_feed")
def video_feed_endpoint():
    logger.info("[MJPEG] 视频流客户端连接")
    def frame_generator():
        while True:
            if state["is_running"] and state["frame"] is not None:
                success, encoded_img = cv2.imencode(
                    '.jpg',
                    state["frame"]
                )
                if success:
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + encoded_img.tobytes() + b'\r\n'
                    )
            import time
            time.sleep(0.04)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/latest_frame")
def api_latest_frame():
    if state["frame"] is None:
        return Response(status_code=204)

    success, encoded_img = cv2.imencode('.jpg', state["frame"])
    if not success:
        return Response(status_code=204)

    return Response(
        content=encoded_img.tobytes(),
        media_type="image/jpeg"
    )

@app.post("/api/start")
def api_start_monitoring():
    state["is_running"] = True
    logger.info("[API] 启动监控 class=%s", state["current_class"])
    return {"ok": True}

@app.post("/api/stop")
def api_stop_monitoring():
    state["is_running"] = False
    state["seats"] = []
    state["events"] = []
    state["counts"] = {
        "total": 0,
        "focus": 0,
        "normal": 0
    }
    logger.info("[API] 停止监控")
    return {"ok": True}

@app.get("/api/classes")
def api_classes():
    return {
        "classes": state["class_list"],
        "current": state["current_class"]
    }

@app.post("/api/switch_class")
async def api_switch_class(request: Request):
    body = await request.json()
    class_name = (body or {}).get("class", "")
    if not class_name:
        logger.warning("[API] 切换班级缺少参数")
        return {"ok": False, "error": "缺少班级参数"}
    ok = switch_class(class_name)
    logger.info("[API] 切换班级 %s → ok=%s", class_name, ok)
    return {"ok": ok, "current": state["current_class"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8997
    )
