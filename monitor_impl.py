import os
import json
import base64
import time
import cv2
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from video_stream_util import MockMonitorStream
from pose_engine import PoseEngine

# 1. 路径与目录初始化
ROOT_PATH = Path(__file__).resolve().parents[1]
EVENT_CROP_DIR = ROOT_PATH / "outputs" / "v2" / "event_crops"
LOG_DIR = ROOT_PATH / "outputs" / "v2" / "analysis_logs"

# 确保目录存在
EVENT_CROP_DIR.mkdir(
    parents=True, 
    exist_ok=True
)
LOG_DIR.mkdir(
    parents=True, 
    exist_ok=True
)

# 2. 视频流与全局状态机
video_stream = MockMonitorStream()
initial_frame = video_stream.get_latest_frame()

# 使用标准常量替换魔术数字
_cap_info = cv2.VideoCapture(str(ROOT_PATH / "inputs" / "video" / "test.mp4"))
IMG_W = int(_cap_info.get(cv2.CAP_PROP_FRAME_WIDTH))
IMG_H = int(_cap_info.get(cv2.CAP_PROP_FRAME_HEIGHT))
_cap_info.release()

state = {
    "is_running": False,
    "time": "00:00:00",
    "frame": initial_frame,
    "img_w": IMG_W,
    "img_h": IMG_H,
    "seats": [],
    "events": [],
    "counts": {
        "total": 0,
        "focus": 0,
        "normal": 0
    }
}

websocket_clients = set()

# 3. 核心监测与分析逻辑
def detection_analysis_loop():
    print("AI 引擎正在初始化...")

    # 加载检测模型
    detector = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(ROOT_PATH / "models" / "detect.pt"),
        confidence_threshold=0.25
    )

    # 加载姿态预检模型
    pose_prechecker = PoseEngine(
        str(ROOT_PATH / "models" / "yolo26s-pose.pt")
    )

    # 初始化大模型客户端
    vlm_client = ChatOpenAI(
        model="qwen-vl-max",
        api_key=os.environ.get("ALIYUN_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

    # 读取 Prompt 模版
    sys_prompt_content = open(str(ROOT_PATH / "vl_model_system_prompt.md"), "r", encoding="utf-8").read()
    usr_prompt_tmpl = open(str(ROOT_PATH / "vl_model_user_prompt.md"), "r", encoding="utf-8").read()
    
    cycle_index = 0
    seat_id_counter = 100

    while True:
        if not state["is_running"]:
            time.sleep(0.5)
            continue

        current_frame = state["frame"]
        if current_frame is None:
            continue

        # 第一级：实时检测
        prediction = get_sliced_prediction(
            current_frame,
            detector,
            slice_height=640,
            slice_width=640,
            verbose=0
        )
        
        detections = [p for p in prediction.object_prediction_list if p.category.id == 0]
        new_tracked_seats = []

        for det in detections:
            # 坐标转换展开
            raw_box = det.bbox.to_xyxy()
            box_xyxy = [
                round(raw_box[0], 2),
                round(raw_box[1], 2),
                round(raw_box[2], 2),
                round(raw_box[3], 2)
            ]

            matched = None
            for s in state["seats"]:
                # 极简中心点匹配
                dist_sq = (
                    ((box_xyxy[0] + box_xyxy[2]) / 2 - (s["box"][0] + s["box"][2]) / 2) ** 2 +
                    ((box_xyxy[1] + box_xyxy[3]) / 2 - (s["box"][1] + s["box"][3]) / 2) ** 2
                )
                if dist_sq < 3000:
                    matched = s
                    break

            if matched:
                matched["box"] = box_xyxy
                new_tracked_seats.append(matched)
            else:
                seat_id_counter += 1
                new_tracked_seats.append({
                    "seat_id": seat_id_counter,
                    "seat_code": f"S{len(new_tracked_seats) + 1:02d}",
                    "box": box_xyxy,
                    "status": "NORMAL"
                })
        
        state["seats"] = new_tracked_seats

        # 第二/三级：姿态与批量 AI 复核
        if cycle_index % 3 == 0 and state["seats"]:
            poses = pose_prechecker.detect_poses_batch(current_frame, state["seats"])
            suspected = []
            
            for i, (p_status, _) in enumerate(poses):
                if i >= len(state["seats"]): break
                s = state["seats"][i]
                if p_status in ["SUSPECTED", "UNCERTAIN"]:
                    suspected.append(s)
                else:
                    s["status"] = p_status

            if suspected:
                print(f"发起批量复核，人数: {len(suspected)}")
                _, buffer = cv2.imencode('.jpg', current_frame)
                img_b64 = base64.b64encode(buffer).decode('utf-8')
                
                targets_text = ""
                for s in suspected:
                    targets_text += f"- seat_id: {s['seat_id']}, box: {s['box']}, code: {s['seat_code']}\n"

                user_msg = usr_prompt_tmpl.replace("{{targets_info}}", targets_text)

                try:
                    # AI 分析调用展开
                    response = vlm_client.invoke([
                        SystemMessage(content=sys_prompt_content),
                        HumanMessage(
                            content=[
                                {"type": "text", "text": user_msg},
                                {
                                    "type": "image_url", 
                                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                                }
                            ]
                        )
                    ]).content

                    # 审计日志保存
                    ts_ms = int(time.time() * 1000)
                    log_entry = {
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "raw": response
                    }
                    with open(LOG_DIR / f"audit_{ts_ms}.json", "w", encoding="utf-8") as f_log:
                        json.dump(log_entry, f_log, ensure_ascii=False, indent=2)

                    batch_ans = json.loads(response.strip().strip("```json").strip("```").strip())
                    for ans in batch_ans:
                        for s_obj in state["seats"]:
                            if s_obj["seat_id"] == ans.get("seat_id"):
                                s_obj["status"] = ans["status"]
                                if s_obj["status"] in ["HEAD_DOWN", "DESK_LYING"]:
                                    file_name = f"ev_{ts_ms}_{s_obj['seat_code']}.jpg"
                                    bx = s_obj["box"]
                                    y1, y2 = max(0, int(bx[1])-40), min(state["img_h"], int(bx[3])+40)
                                    x1, x2 = max(0, int(bx[0])-40), min(state["img_w"], int(bx[2])+40)
                                    cv2.imwrite(str(EVENT_CROP_DIR / file_name), current_frame[y1:y2, x1:x2])
                                    
                                    # 推送事件字典展开
                                    state["events"].insert(0, {
                                        "id": time.time(),
                                        "time": time.strftime("%H:%M:%S"),
                                        "seat": s_obj["seat_code"],
                                        "label": ans["label"],
                                        "reason": ans["reason"],
                                        "risk": "高" if ans["risk_level"]=="HIGH" else "中",
                                        "url": f"/event_crops/{file_name}",
                                        "full_ans": response,
                                        "box": bx
                                    })
                except Exception as e:
                    print(f"AI 批量环节异常: {e}")

        # --- 最终状态同步 ---
        state["time"] = time.strftime(
            "%H:%M:%S"
        )

        # 精细化统计
        high_risk_list = [
            e 
            for e in state["events"] 
            if e["risk"] == "高"
        ]

        medium_risk_list = [
            e 
            for e in state["events"] 
            if e["risk"] == "中"
        ]

        state["counts"] = {
            "total": len(
                state["seats"]
            ),
            "focus": len(
                high_risk_list
            ),
            "normal": len(
                medium_risk_list
            )
        }

        cycle_index += 1
        time.sleep(0.1)

def frame_loader_worker():
    """后台视频读取任务"""
    while True:
        state["frame"] = video_stream.get_latest_frame()
        time.sleep(0.04)
