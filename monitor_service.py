import json
import asyncio
import threading
import cv2
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from monitor_impl import state, websocket_clients, frame_loader_worker, detection_analysis_loop, EVENT_CROP_DIR

# 使用 FastAPI 推荐的 lifespan 异步上下文管理器替代过时的 on_event
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 启动后台业务线程
    threading.Thread(
        target=frame_loader_worker, 
        daemon=True
    ).start()
    
    threading.Thread(
        target=detection_analysis_loop, 
        daemon=True
    ).start()
    
    # 2. 启动状态广播协程
    async def status_broadcast_loop():
        while True:
            if websocket_clients:
                # 剔除二进制帧矩阵，仅推送结构化数据
                payload_dict = {
                    "is_running": state["is_running"],
                    "time": state["time"],
                    "img_w": state["img_w"],
                    "img_h": state["img_h"],
                    "seats": state["seats"],
                    "events": state["events"],
                    "counts": state["counts"]
                }
                
                payload_json = json.dumps(payload_dict)
                
                # 并发推送到所有在线客户端
                await asyncio.gather(
                    *[client.send_text(payload_json) for client in websocket_clients],
                    return_exceptions=True
                )
            await asyncio.sleep(1)
            
    # 将协程包装为后台任务
    broadcast_task = asyncio.create_task(status_broadcast_loop())
    
    yield
    
    # 3. 关机清理
    broadcast_task.cancel()

# 初始化 FastAPI 并注入生命周期管理
app = FastAPI(lifespan=lifespan)

# 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# 挂载静态文件访问路由
app.mount(
    "/event_crops", 
    StaticFiles(directory=str(EVENT_CROP_DIR))
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_clients.add(websocket)
    try:
        while True:
            # 持续监听客户端以保持连接
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)
    except:
        websocket_clients.remove(websocket)

@app.get("/video_feed")
def video_feed_endpoint():
    """MJPEG 视频流实时推送接口"""
    def frame_generator():
        while True:
            # 只有开启监控且帧缓存有效时才进行编码分发
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

@app.post("/api/start")
def api_start_monitoring():
    state["is_running"] = True
    return {"ok": True}

@app.post("/api/stop")
def api_stop_monitoring():
    state["is_running"] = False
    # 停止时清空瞬时数据
    state["seats"] = []
    state["events"] = []
    state["counts"] = {
        "total": 0,
        "focus": 0,
        "normal": 0
    }
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    # 启动全系统服务
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000
    )
