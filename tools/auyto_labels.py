import json
import os

# 1. 这里填你已经标好的那个文件
SOURCE_JSON = "event_001_raw.json"

# 2. 这里填你还没标的图片列表
TARGET_IMAGES = ["event_002_raw.png", "event_003_raw.png", "event_004_raw.png"]


def duplicate_annotations():
  if not os.path.exists(SOURCE_JSON):
    print(f"错误：找不到模板文件 {SOURCE_JSON}")
    return

  # 读取模板数据
  with open(SOURCE_JSON, 'r', encoding = 'utf-8') as f:
    template_data = json.load(f)

  for img_name in TARGET_IMAGES:
    # 克隆模板
    new_data = template_data.copy()

    # 修改图片路径和关联信息
    new_data['imagePath'] = img_name
    # 清空 imageData 确保 X-AnyLabeling 重新加载原图
    new_data['imageData'] = None

    # 生成对应的 JSON 文件名
    json_name = os.path.splitext(img_name)[0] + ".json"

    with open(json_name, 'w', encoding = 'utf-8') as f:
      json.dump(new_data, f, indent = 2, ensure_ascii = False)

    print(f"成功生成：{json_name}")


if __name__ == "__main__":
  duplicate_annotations()
  print("所有标注已生成！现在你可以打开 X-AnyLabeling 进行补漏了。")