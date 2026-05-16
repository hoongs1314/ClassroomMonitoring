import json
import asyncio
import threading
import cv2
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from monitor_impl import state, websocket_clients, frame_loader_worker, detection_analysis_loop, vlm_review_worker, EVENT_CROP_DIR

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(
        target=frame_loader_worker, 
        daemon=True
    ).start()
    
    threading.Thread(
        target=detection_analysis_loop, 
        daemon=True
    ).start()

    threading.Thread(
        target=vlm_review_worker,
        daemon=True
    ).start()
    
    async def status_broadcast_loop():
        while True:
            if websocket_clients:
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
                
                await asyncio.gather(
                    *[client.send_text(payload_json) for client in websocket_clients],
                    return_exceptions=True
                )
            await asyncio.sleep(1)
            
    broadcast_task = asyncio.create_task(status_broadcast_loop())
    
    yield
    
    broadcast_task.cancel()

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
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)
    except:
        websocket_clients.remove(websocket)

@app.get("/video_feed")
def video_feed_endpoint():
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
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000
    )
