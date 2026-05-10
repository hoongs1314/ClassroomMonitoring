import os
from pathlib import Path

from v1.pose_utils import PoseConfig

ROOT_DIR = Path(__file__).resolve().parent

VIDEO_REL_PATH = Path("../inputs/video/test.mp4")
VIDEO_FILE = ROOT_DIR / VIDEO_REL_PATH

OUT_DIR = ROOT_DIR / "outputs" / "video_debug"
RAW_DIR = OUT_DIR / "raw_frames"
EVENT_DIR = OUT_DIR / "events"
CROP_DIR = EVENT_DIR / "crops"
DETAIL_DIR = EVENT_DIR / "frame_focus"
MODEL_DIR = ROOT_DIR / "models"

SEAT_JSON_FILE = OUT_DIR / "seat_result.json"
SEAT_MAP_FILE = OUT_DIR / "seat_map.jpg"
FRAME_JSON_FILE = OUT_DIR / "frame_result.json"
EVENT_JSON_FILE = OUT_DIR / "event_result.json"
DESC_JSON_FILE = OUT_DIR / "event_descriptions.json"

DETECT_MODEL = MODEL_DIR / "detect.pt"
POSE_MODEL = MODEL_DIR / "yolo26s-pose.pt"

IMG_SIZE = 3200
DETECT_CONF = 0.15
DETECT_IOU = 0.6
POSE_CONF = 0.15
POSE_IOU = 0.6
SEAT_IMG_SIZE = 960
SEAT_CROP_PAD = 0.9
SEAT_BOX_PAD = 0.5
POSE_MIN_SEAT_OVERLAP = 0.0

FRAME_SEC = 3
SEAT_SEC = 1
SEAT_FRAME_COUNT = 10
EVENT_START_STRONG_FRAMES = 2
EVENT_START_WEAK_FRAMES = 3
EVENT_END_NORMAL_FRAMES = 2

POSE_RULE = PoseConfig(
    keypoint_conf_threshold=0.2,
    strong_suspect_ratio=-0.10,
    weak_suspect_ratio=0.03,
)

QWEN_MODEL = os.getenv("QWEN_VL_MODEL", "qwen3.6-plus")
QWEN_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)


def make_dirs():
    for path in [OUT_DIR, RAW_DIR, EVENT_DIR, CROP_DIR, DETAIL_DIR, MODEL_DIR]:
        path.mkdir(parents=True, exist_ok=True)


# 兼容旧脚本
OUTPUT_DIR = OUT_DIR
RAW_FRAME_DIR = RAW_DIR
EVENT_CROP_DIR = CROP_DIR
FRAME_FOCUS_DIR = DETAIL_DIR
VIDEO_PATH = VIDEO_REL_PATH
MODEL_PATH = POSE_MODEL
CONF = DETECT_CONF
IOU = DETECT_IOU
MODEL_FILE = str(POSE_MODEL)
FRAME_STEP = FRAME_SEC
make_output_dirs = make_dirs
