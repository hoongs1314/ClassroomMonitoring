from pathlib import Path
import time

import cv2
from ultralytics import YOLO

# 输入。
SELECTED_IMAGE_PATHS = [
  Path("inputs/screen/t4.png"),
  Path("inputs/screen/t6.png"),
]

# 输出。
OUTPUT_DIR = Path("outputs/debug_pose_ratio")
OUTPUT_DIR.mkdir(parents = True, exist_ok = True)

# 轻量模型
MODEL_NAME = "yolo26s-pose.pt"
IMG_SIZE = 3200
CONF = 0.06
NMS_IOU = 0.6
# 整图跑完后，再补一刀上半部分，主要是照顾后排和远处的小人。
TOP_CROP_RATIO = 0.65
TOP_CROP_IMG_SIZE = 2240
# 左上窗边那块单独补一次，之前这里比较容易漏人。
WINDOW_CROP = (0.18, 0.05, 0.48, 0.42)
WINDOW_CROP_IMG_SIZE = 1600
WINDOW_CROP_CONF = 0.04

# 第一轮去重偏保守一点，先把明显重复的压掉。
DUPLICATE_IOU = 0.8
DUPLICATE_IOA = 0.85
# 关键点阈值不用太高，不然头发遮脸或者远处学生很容易直接掉掉。
KEYPOINT_CONF_THRESHOLD = 0.2

# 强：负数认定趴桌
STRONG_SUSPECT_RATIO = 0.0
# 弱规则
WEAK_SUSPECT_RATIO = 0.10

# 头部这里不只看 nose，眼睛和耳朵也一起兜底，能少一点漏判。
HEAD_POINT_INDEXES = [0, 1, 2, 3, 4]
LEFT_SHOULDER_INDEX = 5
RIGHT_SHOULDER_INDEX = 6


def put_label(image, text, x, y):
  # 这里用黑底白字，教室这种复杂背景里更不容易看丢。
  font = cv2.FONT_HERSHEY_SIMPLEX
  cv2.putText(image, text, (x, y), font, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
  cv2.putText(image, text, (x, y), font, 0.65, (255, 255, 255), 2, cv2.LINE_AA)


def box_width(box):
  return box[2] - box[0]


def box_height(box):
  return box[3] - box[1]


def box_area(box):
  return max(0.0, box_width(box)) * max(0.0, box_height(box))


def box_center(box):
  # 中心点。
  return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def box_aspect_ratio(box):
  return box_width(box) / max(1.0, box_height(box))


def center_is_close(box1, box2, width_ratio, height_ratio):
  # 这一步不是看绝对距离，而是按较小框的尺寸去看相对距离，
  # 这样远处小人和近处大人都还能共用一套规则。
  center1_x, center1_y = box_center(box1)
  center2_x, center2_y = box_center(box2)
  min_w = max(1.0, min(box_width(box1), box_width(box2)))
  min_h = max(1.0, min(box_height(box1), box_height(box2)))
  return (
      abs(center1_x - center2_x) <= min_w * width_ratio
      and abs(center1_y - center2_y) <= min_h * height_ratio
  )


def x_center_is_close(box1, box2, width_ratio):
  # 有些重复框会上下拉得很开，但横向中心其实还是同一个人。
  center1_x, _ = box_center(box1)
  center2_x, _ = box_center(box2)
  min_w = max(1.0, min(box_width(box1), box_width(box2)))
  return abs(center1_x - center2_x) <= min_w * width_ratio


def calc_box_iou(box1, box2):
  # 标准 IoU，主要用来判断两个框是不是高度重叠。
  ax1, ay1, ax2, ay2 = box1
  bx1, by1, bx2, by2 = box2

  inter_x1 = max(ax1, bx1)
  inter_y1 = max(ay1, by1)
  inter_x2 = min(ax2, bx2)
  inter_y2 = min(ay2, by2)

  inter_w = max(0.0, inter_x2 - inter_x1)
  inter_h = max(0.0, inter_y2 - inter_y1)
  inter_area = inter_w * inter_h

  area1 = box_area(box1)
  area2 = box_area(box2)
  union = area1 + area2 - inter_area

  if union <= 0:
    return 0.0

  return inter_area / union


def calc_box_ioa(box1, box2):
  # 这里用的是交集占较小框面积的比例。
  # 对“大框套小框”这种情况，比单纯看 IoU 更好用。
  ax1, ay1, ax2, ay2 = box1
  bx1, by1, bx2, by2 = box2

  inter_x1 = max(ax1, bx1)
  inter_y1 = max(ay1, by1)
  inter_x2 = min(ax2, bx2)
  inter_y2 = min(ay2, by2)

  inter_w = max(0.0, inter_x2 - inter_x1)
  inter_h = max(0.0, inter_y2 - inter_y1)
  inter_area = inter_w * inter_h

  area1 = box_area(box1)
  area2 = box_area(box2)
  min_area = min(area1, area2)

  if min_area <= 0:
    return 0.0

  return inter_area / min_area


def is_contained_duplicate(box1, box2):
  # 这类情况就是这次重点在抓的：
  # 小框基本完整落在大框里面，但大框只是把同一个人往下多包了一截，
  # 看起来像“半身框 + 错误全身框”一起留下来了。
  ioa = calc_box_ioa(box1, box2)
  if ioa < 0.95:
    return False

  if not x_center_is_close(box1, box2, 0.30):
    return False

  width_ratio = max(box_width(box1), box_width(box2)) / max(1.0, min(box_width(box1), box_width(box2)))
  height_ratio = max(box_height(box1), box_height(box2)) / max(1.0, min(box_height(box1), box_height(box2)))

  return width_ratio <= 1.65 and height_ratio >= 1.45


def should_merge_duplicate(box1, box2, final_pass = False):
  # 两轮去重其实判断的是同一件事，只是最后一轮放得更宽一点。
  iou = calc_box_iou(box1, box2)
  ioa = calc_box_ioa(box1, box2)
  close_center = center_is_close(box1, box2, 0.45 if final_pass else 0.35, 0.45 if final_pass else 0.35)
  very_close_center = center_is_close(box1, box2, 0.30, 0.30)
  contained_duplicate = is_contained_duplicate(box1, box2)

  if iou >= DUPLICATE_IOU:
    return True

  if ioa >= DUPLICATE_IOA and close_center:
    return True

  if contained_duplicate:
    return True

  if not final_pass:
    return False

  strong_overlap = iou >= 0.40 or ioa >= 0.60
  nested_overlap = ioa >= 0.50 and very_close_center

  return (
      iou >= 0.55
      or (ioa >= 0.70 and close_center)
      or (strong_overlap and close_center)
      or nested_overlap
  )


def choose_better_box(item1, item2):
  # 两个框确定冲突时，这里负责决定留谁。
  area1 = box_area(item1["box"])
  area2 = box_area(item2["box"])
  conf1 = item1["confidence"]
  conf2 = item2["confidence"]
  ratio1, valid1, _ = calc_head_shoulder_ratio(
    item1["kpts_xy"], item1["kpts_conf"], box_height(item1["box"])
  )
  ratio2, valid2, _ = calc_head_shoulder_ratio(
    item2["kpts_xy"], item2["kpts_conf"], box_height(item2["box"])
  )

  if valid1 != valid2:
    return item1 if valid1 else item2

  area_ratio = max(area1, area2) / max(1.0, min(area1, area2))

  # 同一个人有多个候选框时，如果其中一个明显更“低头”，就优先留它，
  # 不然补检出来的趴桌框很容易又被偏正常的框盖回去。
  if valid1 and valid2 and area_ratio <= 1.35 and abs(ratio1 - ratio2) >= 0.025:
    return item1 if ratio1 <= ratio2 else item2

  # 如果已经是这种“小框被高框吞进去”的形态，直接留更紧的小框。
  if is_contained_duplicate(item1["box"], item2["box"]):
    return item1 if area1 <= area2 else item2

  # 面积差明显时，直接优先留更紧的小框。
  if area_ratio >= 1.25:
    return item1 if area1 <= area2 else item2

  # 面积差没那么夸张，但置信度也差不多时，还是留小框。
  if abs(conf1 - conf2) <= 0.20:
    return item1 if area1 <= area2 else item2

  # 保底，留更高置信度
  return item1 if conf1 >= conf2 else item2


def deduplicate_items(items, final_pass = False):
  # 去重统一走这里，前后两轮只差“最后一轮更宽松一点”。
  if len(items) <= 1:
    return items

  order = sorted(items, key = lambda item: item["confidence"], reverse = True)
  kept = []

  for current in order:
    keep_current = True
    for index, kept_item in enumerate(kept):
      if not should_merge_duplicate(current["box"], kept_item["box"], final_pass = final_pass):
        continue

      better = choose_better_box(current, kept_item)
      if better is current:
        kept[index] = current
      keep_current = False
      break

    if keep_current:
      kept.append(current)

  kept.sort(key = lambda item: item["box"][0] + item["box"][1] * 0.01)
  return kept


def remove_cross_person_boxes(items):
  # 这一步专门处理一种常见误检：
  # 一个大框横着跨到两个人身上，而两边其实已经各有自己的小框了。
  if len(items) <= 2:
    return items

  removed_indexes = set()
  for index, current in enumerate(items):
    current_box = current["box"]
    current_width = box_width(current_box)
    current_height = box_height(current_box)
    current_area = box_area(current_box)
    current_center_x, _ = box_center(current_box)
    left_neighbors = []
    right_neighbors = []

    for other_index, other in enumerate(items):
      if index == other_index:
        continue

      other_box = other["box"]
      ioa = calc_box_ioa(current_box, other_box)
      iou = calc_box_iou(current_box, other_box)
      if ioa < 0.18 and iou < 0.10:
        continue

      same_row = center_is_close(current_box, other_box, 1.20, 0.55)
      if not same_row:
        continue

      other_area = box_area(other_box)
      if other_area >= current_area * 0.92:
        continue

      other_center_x, _ = box_center(other_box)
      if other_center_x < current_center_x:
        left_neighbors.append(other)
      else:
        right_neighbors.append(other)

    if not left_neighbors or not right_neighbors:
      continue

    left = max(left_neighbors, key = lambda item: item["confidence"])
    right = max(right_neighbors, key = lambda item: item["confidence"])
    left_box = left["box"]
    right_box = right["box"]
    left_width = box_width(left_box)
    right_width = box_width(right_box)
    left_height = box_height(left_box)
    right_height = box_height(right_box)
    left_area = box_area(left_box)
    right_area = box_area(right_box)
    left_center_x, _ = box_center(left_box)
    right_center_x, _ = box_center(right_box)
    average_small_width = (left_width + right_width) / 2.0
    average_small_height = (left_height + right_height) / 2.0
    combined_area = left_area + right_area
    horizontal_span = right_center_x - left_center_x

    # 如果当前框同时压住左右两个邻居，
    # 而且自己明显更宽、更像“把两个人并成一个”的样子，就删掉它。
    if (
        horizontal_span >= average_small_width * 0.80
        and current_width >= average_small_width * 1.45
        and current_height <= average_small_height * 1.45
        and combined_area >= current_area * 0.70
    ):
      removed_indexes.add(index)

  return [item for index, item in enumerate(items) if index not in removed_indexes]


def is_big_side_box(box, image_width, image_height):
  # 这类框大多不是学生，而是边缘位置的老师或误检大框。
  x1, y1, _, _ = box
  width = box_width(box)
  height = box_height(box)
  area = box_area(box)
  center_x, _ = box_center(box)

  if height <= 0 or width <= 0:
    return False

  height_ratio = height / image_height
  width_height_ratio = width / height
  center_ratio = center_x / image_width
  top_ratio = y1 / image_height
  width_ratio = width / image_width
  area_ratio = area / (image_width * image_height)

  if (
      height_ratio >= 0.33
      and width_height_ratio <= 0.58
      and (center_ratio <= 0.28 or center_ratio >= 0.90)
  ):
    return True

  # 还有一种是上方或侧边冒出来的超大框，也顺手过滤掉。
  if top_ratio >= 0.60 and width_ratio >= 0.28 and area_ratio >= 0.08:
    return True

  return False


def is_non_student_box(box, image_width, image_height):
  # 这里补几条很朴素的规则，把明显不像学生的框拦掉。
  x1, y1, x2, y2 = box
  width = box_width(box)
  height = box_height(box)
  area = box_area(box)

  if width <= 0 or height <= 0:
    return False

  left_ratio = x1 / image_width
  top_ratio = y1 / image_height
  width_ratio = width / image_width
  height_ratio = height / image_height
  width_height_ratio = width / height
  area_ratio = area / (image_width * image_height)

  if (
      left_ratio <= 0.14
      and top_ratio >= 0.25
      and height_ratio >= 0.32
      and width_height_ratio <= 0.70
  ):
    return True

  # 底部横着铺开的超大框，通常也是误检，不留着影响观感。
  if top_ratio >= 0.70 and width_ratio >= 0.24 and area_ratio >= 0.05:
    return True

  return False


def collect_result(result, offset_x = 0.0, offset_y = 0.0):
  # 统一把模型输出整理成同一种结构，
  # 这样整图、上半图、窗边补图后面都能直接拼起来用。
  if result.boxes is None or result.keypoints is None:
    return []

  boxes = result.boxes.xyxy.cpu().tolist()
  confidences = result.boxes.conf.cpu().tolist()
  keypoints_xy = result.keypoints.xy.cpu().tolist()
  keypoints_conf = result.keypoints.conf.cpu().tolist()

  return [
    {
      "box": [
        box[0] + offset_x,
        box[1] + offset_y,
        box[2] + offset_x,
        box[3] + offset_y,
      ],
      "confidence": float(confidence),
      "kpts_xy": [
        [point[0] + offset_x, point[1] + offset_y]
        for point in points_xy
      ],
      "kpts_conf": [float(value) for value in points_conf],
    }
    for box, confidence, points_xy, points_conf in zip(
      boxes, confidences, keypoints_xy, keypoints_conf
    )
  ]


def get_head_y(kpts_xy, kpts_conf):
  # 头部位置这里取一个“能看到的头部关键点平均值”，
  # 不强行只盯鼻子，这样长发遮挡时会稳一点。
  visible_y = []
  for index in HEAD_POINT_INDEXES:
    if float(kpts_conf[index]) >= KEYPOINT_CONF_THRESHOLD:
      visible_y.append(float(kpts_xy[index][1]))

  if not visible_y:
    return None

  return sum(visible_y) / len(visible_y)


def calc_head_shoulder_ratio(kpts_xy, kpts_conf, bbox_height):
  # 这里是 demo 里的核心规则：
  # 看头部到肩膀的相对高度，粗略判断是不是低头比较厉害。
  if bbox_height <= 0:
    return None, False, "bad_bbox"

  head_y = get_head_y(kpts_xy, kpts_conf)
  if head_y is None:
    return None, False, "head_low"

  left_shoulder_conf = float(kpts_conf[LEFT_SHOULDER_INDEX])
  right_shoulder_conf = float(kpts_conf[RIGHT_SHOULDER_INDEX])
  if left_shoulder_conf < KEYPOINT_CONF_THRESHOLD:
    return None, False, "left_shoulder_low"
  if right_shoulder_conf < KEYPOINT_CONF_THRESHOLD:
    return None, False, "right_shoulder_low"

  left_shoulder_y = float(kpts_xy[LEFT_SHOULDER_INDEX][1])
  right_shoulder_y = float(kpts_xy[RIGHT_SHOULDER_INDEX][1])
  shoulder_y = (left_shoulder_y + right_shoulder_y) / 2.0

  ratio = (shoulder_y - head_y) / bbox_height
  return ratio, True, "ok"


def classify_pose(ratio, valid, box = None, confidence = None):
  # 这里只给三档，够 demo 看效果就行。
  if not valid or ratio is None:
    return "INVALID"
  if ratio < STRONG_SUSPECT_RATIO:
    return "STRONG"
  if ratio < WEAK_SUSPECT_RATIO:
    return "WEAK"
  if box is not None and ratio < 0.13 and box_aspect_ratio(box) < 0.65:
    return "WEAK"
  if (
      box is not None
      and confidence is not None
      and ratio < 0.17
      and box_aspect_ratio(box) < 0.80
      and 0.20 <= confidence <= 0.30
  ):
    return "WEAK"
  return "NORMAL"


def get_box_color(status):
  # 红黄绿就够了，现场看图时一眼能分出来。
  if status == "STRONG":
    return (0, 0, 255)
  if status == "WEAK":
    return (0, 255, 255)
  if status == "NORMAL":
    return (0, 255, 0)
  return (128, 128, 128)


def process_image(model, image_path):
  # 单张图的完整流程都放这里：
  # 读图 -> 三次检测 -> 去重 -> 过滤 -> 画图 -> 保存。
  image = cv2.imread(str(image_path))
  if image is None:
    print(f"图片读取失败：{image_path}")
    return

  image_height, image_width = image.shape[:2]
  start_time = time.time()
  full_result = model.predict(
    source = str(image_path),
    imgsz = IMG_SIZE,
    conf = CONF,
    iou = NMS_IOU,
    verbose = False,
  )[0]

  # 上半部分补一刀，主要是为了远处学生。
  crop_bottom = int(image_height * TOP_CROP_RATIO)
  top_image = image[:crop_bottom, :]
  top_result = model.predict(
    source = top_image,
    imgsz = TOP_CROP_IMG_SIZE,
    conf = CONF,
    iou = NMS_IOU,
    verbose = False,
  )[0]

  # 左上窗边区域单独补一刀，这里之前最容易漏。
  win_x1 = int(image_width * WINDOW_CROP[0])
  win_y1 = int(image_height * WINDOW_CROP[1])
  win_x2 = int(image_width * WINDOW_CROP[2])
  win_y2 = int(image_height * WINDOW_CROP[3])
  window_image = image[win_y1:win_y2, win_x1:win_x2]
  window_result = model.predict(
    source = window_image,
    imgsz = WINDOW_CROP_IMG_SIZE,
    conf = WINDOW_CROP_CONF,
    iou = NMS_IOU,
    verbose = False,
  )[0]
  elapsed = time.time() - start_time

  items = (
      collect_result(full_result)
      + collect_result(top_result)
      + collect_result(window_result, offset_x = win_x1, offset_y = win_y1)
  )

  if not items:
    print(f"{image_path.name}：没有检测到人体或关键点")
    return

  # 先做一轮基础去重。
  deduped_items = deduplicate_items(items)

  # 再把明显不像学生的框过滤掉。
  removed_large_boxes = 0
  filtered_items = []
  for item in deduped_items:
    box = item["box"]
    if (
        is_big_side_box(box, image_width, image_height)
        or is_non_student_box(box, image_width, image_height)
    ):
      removed_large_boxes += 1
      continue
    filtered_items.append(item)

  # 最后再做一轮输出前的重叠清理。
  final_items = deduplicate_items(filtered_items, final_pass = True)
  first_pass_removed = len(items) - len(deduped_items)
  final_overlap_removed = len(filtered_items) - len(final_items)

  print(
    f"{image_path.name} 用时 {elapsed:.2f}s，"
    f"原始人数 {len(items)}，"
    f"第一轮去重移除 {first_pass_removed}，"
    f"大框过滤移除 {removed_large_boxes}，"
    f"最终重叠移除 {final_overlap_removed}，"
    f"最终人数 {len(final_items)}"
  )

  debug_image = image.copy()
  status_count = { "NORMAL": 0, "WEAK": 0, "STRONG": 0, "INVALID": 0 }

  for display_index, item in enumerate(final_items, start = 1):
    x1, y1, x2, y2 = item["box"]
    bbox_height = y2 - y1

    # 先算比例，再给状态，最后决定框颜色和标签内容。
    ratio, valid, reason = calc_head_shoulder_ratio(
      kpts_xy = item["kpts_xy"],
      kpts_conf = item["kpts_conf"],
      bbox_height = bbox_height,
    )
    status = classify_pose(ratio, valid, item["box"], item["confidence"])

    # 关键点明显不够的框，直接不画了，避免调试图里出现一堆灰框干扰判断。
    if status == "INVALID":
      continue

    status_count[status] += 1

    x1_i, y1_i, x2_i, y2_i = map(int, [x1, y1, x2, y2])
    color = get_box_color(status)
    cv2.rectangle(debug_image, (x1_i, y1_i), (x2_i, y2_i), color, 2)

    label = f"ID:{display_index} {status} r:{ratio:.3f}"

    put_label(debug_image, label, max(0, x1_i), max(25, y1_i - 8))

  output_path = OUTPUT_DIR / f"{image_path.stem}_debug.jpg"
  cv2.imwrite(str(output_path), debug_image)

  print(
    "统计："
    f" NORMAL={status_count['NORMAL']},"
    f" WEAK={status_count['WEAK']},"
    f" STRONG={status_count['STRONG']},"
    f" INVALID={status_count['INVALID']}"
  )
  print(f"调试图已保存：{output_path}")


def main():
  # 入口就做最基本的检查和循环，不额外塞别的逻辑。
  missing = [path for path in SELECTED_IMAGE_PATHS if not path.exists()]
  if missing:
    print("以下图片不存在：")
    for path in missing:
      print(f"- {path}")
    return

  print(f"加载模型：{MODEL_NAME}")
  model = YOLO(MODEL_NAME)

  for image_path in SELECTED_IMAGE_PATHS:
    print(f"\n开始处理：{image_path}")
    process_image(model, image_path)


if __name__ == "__main__":
  main()
