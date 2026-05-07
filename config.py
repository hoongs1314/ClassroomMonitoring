import os
from pathlib import Path

from pose_utils import PoseConfig

ROOT_DIR = Path(__file__).resolve().parent

VIDEO_REL_PATH = Path("inputs/video/test.mp4")
VIDEO_FILE = ROOT_DIR / VIDEO_REL_PATH

OUTPUT_DIR = ROOT_DIR / "outputs/video_debug"
RAW_FRAME_DIR = OUTPUT_DIR / "raw_frames"
EVENT_DIR = OUTPUT_DIR / "events"
EVENT_CROP_DIR = EVENT_DIR / "crops"
FRAME_FOCUS_DIR = EVENT_DIR / "frame_focus"

FRAME_JSON_FILE = OUTPUT_DIR / "frame_result.json"
EVENT_JSON_FILE = OUTPUT_DIR / "event_result.json"
DESC_JSON_FILE = OUTPUT_DIR / "event_descriptions.json"

MODEL_PATH = ROOT_DIR / "yolo26n.pt"
IMG_SIZE = 3200
CONF = 0.15
IOU = 0.7
FRAME_SEC = 3
EVENT_GAP_SEC = FRAME_SEC * 1.5

POSE_RULE = PoseConfig(
    keypoint_conf_threshold=0.3,
    strong_suspect_ratio=0.0,
    weak_suspect_ratio=0.10,
)

QWEN_MODEL = "qwen3.5-plus-2026-02-15"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def make_output_dirs():
    for path in [OUTPUT_DIR, RAW_FRAME_DIR, EVENT_DIR, EVENT_CROP_DIR, FRAME_FOCUS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


# 兼容旧名字，避免旧脚本直接跑坏
VIDEO_PATH = VIDEO_REL_PATH
FRAME_JSON = FRAME_JSON_FILE
EVENT_JSON = EVENT_JSON_FILE
DESC_JSON = DESC_JSON_FILE
MODEL_FILE = str(MODEL_PATH)
FRAME_STEP = FRAME_SEC
EVENT_GAP = EVENT_GAP_SEC
POSE_CFG = POSE_RULE
QWEN_URL = QWEN_BASE_URL
make_dirs = make_output_dirs
