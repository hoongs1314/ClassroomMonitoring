import os
import json
import base64
import cv2
import numpy as np
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

# --- 路径配置 ---
ROOT_PATH = Path(__file__).resolve().parents[1]
VIDEO_PATH = str(ROOT_PATH / "inputs/video/test.mp4")
MODEL_PATH = str(ROOT_PATH / "models/detect.pt")
OUTPUT_ROOT = str(ROOT_PATH / "outputs/v2/monitor_vl")
SYSTEM_PROMPT_PATH = str(ROOT_PATH / "vlm_system_prompt.md")
USER_PROMPT_PATH = str(ROOT_PATH / "vlm_user_prompt.md")

INTERVAL = 10.0  # 隔10秒跑一次
CONF_THRESHOLD = 0.25

# --- 初始化大模型 ---
def get_llm():
    return ChatOpenAI(
        model="qwen-vl-max",
        api_key=os.environ["ALIYUN_API_KEY"],
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

# --- 初始化检测模型 ---
def get_sahi_model():
    return AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=MODEL_PATH,
        confidence_threshold=CONF_THRESHOLD,
        device="cpu", 
    )

# --- 转Base64用于上传 ---
def encode_image_base64(img_ndarray):
    _, buffer = cv2.imencode('.jpg', img_ndarray)
    return base64.b64encode(buffer).decode('utf-8')

def main():
    # 创建输出文件夹
    output_dir = Path(OUTPUT_ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 加载提示词
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        sys_prompt = f.read()
    with open(USER_PROMPT_PATH, "r", encoding="utf-8") as f:
        user_prompt_tmpl = f.read()

    sahi_model = get_sahi_model()
    llm = get_llm()
    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    curr_sec = 0.0
    while curr_sec < duration:
        print(f"\n正在处理 {curr_sec:.1f} 秒这一帧...")
        
        cap.set(cv2.CAP_PROP_POS_MSEC, curr_sec * 1000)
        ret, frame = cap.read()
        if not ret: break
        
        # 运行切片检测
        result = get_sliced_prediction(
            frame, sahi_model, 
            slice_height=640, slice_width=640, 
            overlap_height_ratio=0.2, overlap_width_ratio=0.2,
            verbose=0
        )
        
        seats = []
        for i, pred in enumerate(result.object_prediction_list):
            if pred.category.id != 0: continue 
            box = [round(v, 2) for v in pred.bbox.to_xyxy()]
            seats.append({
                "seat_id": i + 1,
                "seat_code": f"S{i+1:02d}",
                "box": box,
                "score": round(pred.score.value, 4)
            })

        # 文件命名格式
        timestamp_str = f"t_{int(curr_sec):04d}s"
        frame_path = output_dir / f"{timestamp_str}_raw.jpg"
        map_path = output_dir / f"{timestamp_str}_map.jpg"
        json_path = output_dir / f"{timestamp_str}_seats.json"
        
        # 准备绿色细线标记图
        map_img = frame.copy()
        for s in seats:
            b = [int(v) for v in s["box"]]
            # 线宽设为1，颜色用绿色
            cv2.rectangle(map_img, (b[0], b[1]), (b[2], b[3]), (0, 255, 0), 1)
            cv2.putText(map_img, s["seat_code"], (b[0], b[1]-4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        
        # 保存各种产物
        cv2.imwrite(str(frame_path), frame)
        cv2.imwrite(str(map_path), map_img)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(seats, f, ensure_ascii=False, indent=2)

        # 传给大模型的必须是无遮挡的原图
        img_b64 = encode_image_base64(frame)

        # 存放这一帧的 AI 分析结果
        analysis_results = []

        # 选前几个座位跑一下大模型测试
        for s in seats[:3]:
            print(f"分析 {s['seat_code']} 号座位...")
            user_prompt = user_prompt_tmpl.replace("{{seat_id}}", str(s["seat_id"])) \
                                         .replace("{{frame_time}}", timestamp_str) \
                                         .replace("{{box}}", str(s["box"])) \
                                         .replace("{{detect_confidence}}", str(s["score"]))

            messages = [
                SystemMessage(content=sys_prompt),
                HumanMessage(content=[
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ])
            ]

            try:
                response = llm.invoke(messages)
                content = response.content
                print(f"[{s['seat_code']} 结果]: {content}")

                # 尝试把返回的字符串转成 JSON 对象存起来
                try:
                    # 去掉可能存在的 markdown 代码块标记
                    clean_content = content.strip().strip("```json").strip("```").strip()
                    analysis_results.append(json.loads(clean_content))
                except:
                    analysis_results.append({"seat_id": s["seat_id"], "raw_output": content})

            except Exception as e:
                print(f"[{s['seat_code']} 报错]: {e}")
                analysis_results.append({"seat_id": s["seat_id"], "error": str(e)})

        # 把这一帧所有座位的分析结果存成 json
        analysis_path = output_dir / f"{timestamp_str}_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(analysis_results, f, ensure_ascii=False, indent=2)

        curr_sec += INTERVAL


    cap.release()
    print("\n监控任务搞定啦。")

if __name__ == "__main__":
    main()
