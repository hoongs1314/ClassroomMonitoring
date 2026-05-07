import cv2
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def extract_frames_v2(video_path, output_folder, interval_seconds = 3):
  if not os.path.exists(output_folder):
    os.makedirs(output_folder)

  video = cv2.VideoCapture(video_path)
  fps = video.get(cv2.CAP_PROP_FPS)
  total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

  # 计算每隔多少帧取一张
  frame_interval = int(fps * interval_seconds)

  current_frame = 0
  saved_count = 0

  while current_frame < total_frames:
    # 设置视频读取的位置（直接跳到目标帧）
    video.set(cv2.CAP_PROP_POS_FRAMES, current_frame)

    success, frame = video.read()
    if not success:
      break

    image_name = f"frame_{saved_count:04d}.jpg"
    cv2.imwrite(os.path.join(output_folder, image_name), frame)

    print(f"已保存第 {current_frame} 帧 (约第 {saved_count * interval_seconds} 秒)")

    # 核心：计算下一个目标帧的位置
    current_frame += frame_interval
    saved_count += 1

  video.release()
  print("提取完成！")

input_video = str(ROOT_DIR / "inputs" / "video" / "major01.mp4")
output_dir = str(ROOT_DIR / "dataset" / "v2")
extract_frames_v2(input_video, output_dir, interval_seconds = 3)
