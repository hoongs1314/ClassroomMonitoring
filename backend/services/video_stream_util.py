import logging
import cv2
import threading
from pathlib import Path

from core.paths import REPO_ROOT

logger = logging.getLogger("monitor.video")

ROOT_PATH = REPO_ROOT


class MockMonitorStream:
	def __init__(self, video_path = None):
		self.cap = None
		self.video_path = str(video_path) if video_path else str(ROOT_PATH / "inputs/test.mp4")
		# 上锁，防止切换视频出错
		self._lock = threading.Lock()
		self.open_video()

	def get_latest_frame(self):
		"""获取最后一帧"""
		with self._lock:
			ret, frame = self.cap.read()
			if not ret:
				# 播完了回第0帧循环播
				self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
				frame = self.cap.read()[1]
			return frame

	def switch_video(self, video_path):
		"""切换视频"""
		with self._lock:
			old_name = Path(self.video_path).name
			self.video_path = str(video_path)
			# 释放当前视频读取器
			self.cap.release()
			self.open_video()
			logger.info("[Video] 视频切换成功: %s → %s", old_name, Path(video_path).name)

	# 打开视频
	def open_video(self):
		# 新读取器
		self.cap = cv2.VideoCapture(self.video_path)
		if not self.cap.isOpened():
			logger.error("视频无法打开: %s", self.video_path)
		else:
			fps = self.cap.get(cv2.CAP_PROP_FPS)
			frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
			# %.0f 取整
			logger.info("[Video] 视频已加载: %s %.0ffps, %.0f帧", Path(self.video_path).name, fps, frames)

	# 关闭视频流
	def close(self):
		with self._lock:
			self.cap.release()
