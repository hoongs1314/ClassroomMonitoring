import logging
import cv2
import threading
from pathlib import Path

logger = logging.getLogger("monitor.video")

ROOT_PATH = Path(__file__).resolve().parent

class MockMonitorStream:
    def __init__(self, video_path=None):
        self.video_path = str(video_path) if video_path else str(ROOT_PATH / "inputs/test.mp4")
        self._lock = threading.Lock()
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            logger.error("视频文件打不开: %s", self.video_path)
        else:
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
            logger.info("[视频] 已打开: %s (%.0ffps, %.0f帧)", Path(self.video_path).name, fps, frames)

    def get_latest_frame(self):
        with self._lock:
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            return frame

    def switch_video(self, video_path):
        with self._lock:
            logger.info("[视频] 切换: %s → %s", Path(self.video_path).name, Path(video_path).name)
            self.video_path = str(video_path)
            self.cap.release()
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                logger.error("视频文件打不开: %s", video_path)
            else:
                fps = self.cap.get(cv2.CAP_PROP_FPS)
                frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
                logger.info("[视频] 已切换: %s (%.0ffps, %.0f帧)", Path(self.video_path).name, fps, frames)

    def close(self):
        with self._lock:
            self.cap.release()
