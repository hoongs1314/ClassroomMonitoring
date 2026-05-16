import base64
import json
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# 硬编码路径
SEATS_JSON_PATH = r"E:\Master\MasterProjects\ClassroomMonitoring\outputs\v2\seats_sahi_v3\seats.json"
SEAT_MAP_PATH = r"E:\Master\MasterProjects\ClassroomMonitoring\outputs\v2\seats_sahi_v3\seat_map.jpg"
SYSTEM_PROMPT_PATH = r"/vlm_system_prompt.md"
USER_PROMPT_PATH = r"/vlm_user_prompt.md"

# 读取数据
with open(SEATS_JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)
with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
    sys_prompt = f.read()
with open(USER_PROMPT_PATH, "r", encoding="utf-8") as f:
    user_prompt_tmpl = f.read()

# 准备第一个座位的参数 (使用 seats 列表下的 box)
target_seat = data["seats"][0]
user_prompt = user_prompt_tmpl.replace("{{seat_id}}", str(target_seat["seat_id"])) \
                             .replace("{{frame_time}}", "00:00:00") \
                             .replace("{{box}}", str(target_seat["box"])) \
                             .replace("{{detect_confidence}}", str(target_seat["avg_conf"]))

# 图像 Base64 编码
with open(SEAT_MAP_PATH, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode("utf-8")

# 初始化 ChatOpenAI (阿里云兼容模式)
llm = ChatOpenAI(
    model="qwen-vl-max",
    api_key=os.environ["ALIYUN_API_KEY"], # 强制要求环境变量
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)


# 调用模型
messages = [
    SystemMessage(content=sys_prompt),
    HumanMessage(content=[
        {"type": "text", "text": user_prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
    ])
]

print(f"Analyzing Seat: {target_seat['seat_code']} using full seat_map.jpg...")
print(llm.invoke(messages).content)
