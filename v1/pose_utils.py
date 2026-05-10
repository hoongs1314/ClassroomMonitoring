from dataclasses import dataclass
from typing import Optional, Tuple

import cv2


@dataclass
class PoseRatioResult:
    ratio: Optional[float]
    valid: bool
    reason: str


@dataclass
class PoseConfig:
    keypoint_conf_threshold: float = 0.3
    strong_suspect_ratio: float = 0.0
    weak_suspect_ratio: float = 0.10


class PoseDebugUtils:
    """
    姿态分析公共工具类。

    负责：
    1. 计算头肩比例 head_shoulder_ratio
    2. 根据 ratio 分类 NORMAL / WEAK / STRONG / INVALID
    3. 绘制标签和框
    """

    def __init__(self, config: PoseConfig):
        self.config = config

    def calc_head_shoulder_ratio(self, kpts_xy, kpts_conf, bbox_height: float) -> PoseRatioResult:
        """
        计算头肩距离比例。

        使用关键点：
        - 0: nose
        - 5: left_shoulder
        - 6: right_shoulder

        图像坐标中：
        - y 越大，位置越靠下
        - 正常情况下 nose_y 应该小于 shoulder_y
        - 如果 nose_y 接近或低于 shoulder_y，可能是低头/趴桌
        """
        nose_conf = float(kpts_conf[0])
        left_shoulder_conf = float(kpts_conf[5])
        right_shoulder_conf = float(kpts_conf[6])

        if nose_conf < self.config.keypoint_conf_threshold:
            return PoseRatioResult(None, False, "nose_low")

        if left_shoulder_conf < self.config.keypoint_conf_threshold:
            return PoseRatioResult(None, False, "left_shoulder_low")

        if right_shoulder_conf < self.config.keypoint_conf_threshold:
            return PoseRatioResult(None, False, "right_shoulder_low")

        if bbox_height <= 0:
            return PoseRatioResult(None, False, "bad_bbox")

        nose_y = float(kpts_xy[0][1])
        left_shoulder_y = float(kpts_xy[5][1])
        right_shoulder_y = float(kpts_xy[6][1])

        shoulder_y = (left_shoulder_y + right_shoulder_y) / 2.0
        head_shoulder_distance = shoulder_y - nose_y
        ratio = head_shoulder_distance / bbox_height

        return PoseRatioResult(ratio, True, "ok")

    def classify_pose_by_ratio(self, ratio_result: PoseRatioResult) -> str:
        """
        根据头肩比例做临时姿态分类。

        注意：
        这是 Demo 调试规则，不是最终准确行为识别。
        """
        if not ratio_result.valid or ratio_result.ratio is None:
            return "INVALID"

        if ratio_result.ratio < self.config.strong_suspect_ratio:
            return "STRONG"

        if ratio_result.ratio < self.config.weak_suspect_ratio:
            return "WEAK"

        return "NORMAL"

    @staticmethod
    def get_box_color(pose_status: str) -> Tuple[int, int, int]:
        """
        根据分类返回框颜色。
        OpenCV 使用 BGR 顺序。
        """
        if pose_status == "STRONG":
            return 0, 0, 255       # 红色：强疑似低头/趴桌
        if pose_status == "WEAK":
            return 0, 255, 255     # 黄色：姿态偏低，待观察
        if pose_status == "NORMAL":
            return 0, 255, 0       # 绿色：正常
        return 128, 128, 128       # 灰色：关键点不足/无效

    @staticmethod
    def put_label(image, text: str, x: int, y: int):
        """
        在图像上绘制文字。
        黑色描边 + 白色文字，避免背景复杂时看不清。
        """
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2

        cv2.putText(
            image,
            text,
            (x, y),
            font,
            font_scale,
            (0, 0, 0),
            thickness + 2,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            text,
            (x, y),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    @staticmethod
    def format_time_file(seconds: float) -> str:
        """
        将秒数格式化为 HH-MM-SS，方便文件命名。
        """
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}-{m:02d}-{s:02d}"

    @staticmethod
    def format_time_display(seconds: float) -> str:
        """
        将秒数格式化为 HH:MM:SS，方便 JSON 展示。
        """
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"