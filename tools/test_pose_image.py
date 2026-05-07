import time
from pathlib import Path
from ultralytics import YOLO

ROOT_DIR = Path(__file__).resolve().parent.parent

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle"
]


def main():
    image_path = ROOT_DIR / "inputs" / "screen" / "t4.png"
    output_dir = ROOT_DIR / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not image_path.exists():
        print(f"图片不存在: {image_path}")
        return

    model = YOLO(str(ROOT_DIR / "yolo26x-pose.pt"))

    start_time = time.time()
    results = model.predict(
        source=str(image_path),
        imgsz=3200,
        conf=0.25,
        iou=0.6,
        save=True,
        project=str(output_dir),
        name="result",
        exist_ok=True,
        verbose=False,
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
        x1, y1, x2, y2 = box
        bbox_height = y2 - y1

        # 关键点
        person_kpts = keypoints_xy[i]
        # 关键点最小置信度阈值
        person_kpts_conf = keypoints_conf[i]

        visible_count = int((person_kpts_conf > 0.3).sum().item())
        print(f"人体框 xyxy: {box}")
        print(f"人体框高度 bbox_height: {bbox_height:.2f}")
        print(f"可见关键点数量: {visible_count}")
        print(f"可见关键点: {person_kpts}")

        # COCO 17 点编号：
        # 0 nose
        # 5 left_shoulder
        # 6 right_shoulder
        nose = person_kpts[0]
        left_shoulder = person_kpts[5]
        right_shoulder = person_kpts[6]

        nose_conf = float(person_kpts_conf[0])
        left_shoulder_conf = float(person_kpts_conf[5])
        right_shoulder_conf = float(person_kpts_conf[6])

        print(f"nose_conf: {nose_conf:.3f}")
        print(f"left_shoulder_conf: {left_shoulder_conf:.3f}")
        print(f"right_shoulder_conf: {right_shoulder_conf:.3f}")

        # 如果鼻子和左右肩置信度太低，先不计算
        if nose_conf < 0.3 or left_shoulder_conf < 0.3 or right_shoulder_conf < 0.3:
            print("头肩关键点置信度不足，暂不计算头肩比例")
            continue

        nose_y = float(nose[1])
        left_shoulder_y = float(left_shoulder[1])
        right_shoulder_y = float(right_shoulder[1])
        shoulder_y = (left_shoulder_y + right_shoulder_y) / 2

        # 图像坐标中，y 越大越靠下
        # 正常情况下 nose_y 应该明显小于 shoulder_y
        head_shoulder_distance = shoulder_y - nose_y

        if bbox_height <= 0:
            print("人体框高度异常，暂不计算")
            continue

        head_shoulder_ratio = head_shoulder_distance / bbox_height

        print(f"nose_y: {nose_y:.2f}")
        print(f"shoulder_y: {shoulder_y:.2f}")
        print(f"head_shoulder_distance: {head_shoulder_distance:.2f}")
        print(f"head_shoulder_ratio: {head_shoulder_ratio:.3f}")


if __name__ == "__main__":
    main()
