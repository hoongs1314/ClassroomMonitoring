from pathlib import Path
import time

from ultralytics import YOLO


def main():
    image_path = Path("inputs/classroom_test.jpg")
    output_dir = Path("outputs/pose_python_test")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not image_path.exists():
        print(f"图片不存在: {image_path}")
        return

    model = YOLO("yolo26x-pose.pt")

    start_time = time.time()
    results = model.predict(
        source=str(image_path),
        imgsz=3200,
        conf=0.15,
        save=True,
        project=str(output_dir),
        name="result",
        exist_ok=True,
        verbose=False
    )
    end_time = time.time()

    result = results[0]

    person_count = 0
    if result.boxes is not None:
        person_count = len(result.boxes)

    print("耗时: {:.2f}秒".format(end_time - start_time))

    print(f"检测到的人数: {person_count}")

    if result.keypoints is None:
        print("没有检测到关键点")
        return

    keypoints_xy = result.keypoints.xy
    keypoints_conf = result.keypoints.conf

    print(f"关键点坐标数组形状: {keypoints_xy.shape}")
    print(f"关键点置信度数组形状: {keypoints_conf.shape}")

    for i in range(person_count):
        print(f"\n第 {i + 1} 个人:")
        box = result.boxes.xyxy[i].tolist()
        print(f"人体框 xyxy: {box}")

        person_kpts = keypoints_xy[i]
        person_kpts_conf = keypoints_conf[i]

        visible_count = int((person_kpts_conf > 0.3).sum().item())
        print(f"可见关键点数量: {visible_count}")


if __name__ == "__main__":
    main()