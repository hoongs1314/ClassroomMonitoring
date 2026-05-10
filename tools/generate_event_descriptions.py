import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from v1.config import DESC_JSON_FILE, EVENT_JSON_FILE, QWEN_BASE_URL, QWEN_MODEL
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

EVENT_JSON_PATH = EVENT_JSON_FILE
DESCRIPTION_JSON_PATH = DESC_JSON_FILE
DEFAULT_QWEN_MODEL = QWEN_MODEL
DEFAULT_DASHSCOPE_BASE_URL = QWEN_BASE_URL


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def image_to_data_url(image_path: str) -> str:
    suffix = Path(image_path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    image_bytes = Path(image_path).read_bytes()
    import base64

    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"


def get_llm() -> ChatOpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY，无法生成异常描述。")

    return ChatOpenAI(
        model=DEFAULT_QWEN_MODEL,
        api_key=api_key,
        base_url=DEFAULT_DASHSCOPE_BASE_URL,
        temperature=0.1,
    )


def build_prompt(event: dict, crop: dict) -> HumanMessage:
    return HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "你在看教室监控中的单个学生异常截图。"
                    "请输出 2 句以内的中文描述。"
                    "第一句描述学生当前动作和姿态。"
                    "第二句说明为什么它会被当成疑似异常。"
                    "如果看起来更像正常低头学习，也要直接指出。"
                    f" 当前事件级别：{event['level']}。"
                    f" 当前检测状态：{crop['status']}。"
                    f" 当前比例值：{crop['ratio']}。"
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": image_to_data_url(crop["image"])},
            },
        ]
    )


def main():
    event_data = load_json(EVENT_JSON_PATH)
    if event_data is None:
        print(f"找不到事件 JSON：{EVENT_JSON_PATH}")
        return

    llm = get_llm()
    store = load_json(DESCRIPTION_JSON_PATH) or {"items": {}}

    for event in event_data["events"]:
        for crop in event.get("event_crops", []):
            cache_key = f"event_{event['event_id']}_person_{crop['person_id']}"
            if cache_key in store["items"]:
                continue

            print(f"生成描述：事件 {event['event_id']} / 学生 {crop['person_id']}")
            response = llm.invoke([build_prompt(event, crop)])
            content = response.content.strip() if isinstance(response.content, str) else str(response.content)
            store["items"][cache_key] = {
                "event_id": event["event_id"],
                "person_id": crop["person_id"],
                "status": crop["status"],
                "ratio": crop["ratio"],
                "description": content,
            }
            save_json(DESCRIPTION_JSON_PATH, store)

    print(f"描述已保存：{DESCRIPTION_JSON_PATH}")


if __name__ == "__main__":
    main()
