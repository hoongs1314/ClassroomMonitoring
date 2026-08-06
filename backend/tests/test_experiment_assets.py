import csv
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
	sys.path.insert(0, str(BACKEND_DIR))


EXPECTED_CLASSES = ["NORMAL", "HEAD_DOWN", "DESK_LYING", "TURNING_HEAD", "EATING"]
IMAGE_SUFFIXES = { ".bmp", ".jpeg", ".jpg", ".png", ".webp" }


class ExperimentAssetTests(unittest.TestCase):
	def test_dataset_split_images_and_labels_are_paired_when_assets_exist(self):
		for split in ("train", "val"):
			image_dir = REPO_ROOT / "dataset" / "images" / split
			label_dir = REPO_ROOT / "dataset" / "labels" / split
			if not image_dir.exists() or not label_dir.exists():
				self.skipTest("本地未提供数据集资产，跳过数据集配对检查")

			image_stems = { path.stem for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES }
			label_stems = { path.stem for path in label_dir.glob("*.txt") }
			self.assertGreater(len(image_stems), 0, f"{split} 集没有图像")
			self.assertEqual(image_stems, label_stems, f"{split} 集图像与 YOLO 标签未一一对应")

	def test_dataset_class_mapping_matches_runtime_contract(self):
		data_file = REPO_ROOT / "dataset" / "classroom_behavior.yaml"
		content = data_file.read_text(encoding = "utf-8")
		names = []
		for line in content.splitlines():
			stripped = line.strip()
			if stripped and stripped[0].isdigit() and ":" in stripped:
				names.append(stripped.split(":", 1)[1].strip())

		self.assertEqual(names, EXPECTED_CLASSES)

	def test_local_training_run_has_parseable_metrics_when_present(self):
		run_dir = REPO_ROOT / "train" / "runs" / "classroom_behavior_class_01"
		if not run_dir.exists():
			self.skipTest("本地未提供训练输出，跳过训练资产检查")

		for relative_path in ("args.yaml", "results.csv", "weights/best.pt", "confusion_matrix.png"):
			self.assertTrue((run_dir / relative_path).is_file(), f"缺少训练产物: {relative_path}")

		with (run_dir / "results.csv").open(encoding = "utf-8", newline = "") as file:
			rows = list(csv.DictReader(file))
		self.assertGreater(len(rows), 0, "results.csv 没有训练记录")
		final_row = rows[-1]
		for metric_name in ("metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)", "metrics/mAP50-95(B)"):
			metric_value = float(final_row[metric_name])
			self.assertGreaterEqual(metric_value, 0.0, f"{metric_name} 不能小于 0")
			self.assertLessEqual(metric_value, 1.0, f"{metric_name} 不能大于 1")
