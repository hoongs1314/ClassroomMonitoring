import cv2
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
VIDEO_PATH = str(ROOT_PATH / "inputs/video/test.mp4")

class MockMonitorStream:
    # 模拟监控
    def __init__(self):
        self.cap = cv2.VideoCapture(VIDEO_PATH)
        if not self.cap.isOpened():
            print("报错：视频文件打不开，请检查路径。")
    def get_latest_frame(self):
        ret, frame = self.cap.read()
        # 循环播放
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
        return frame

    def close(self):
        self.cap.release()
