import sys
import unittest
from pathlib import Path

import numpy as np


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
	sys.path.insert(0, str(BACKEND_DIR))

from services import monitor_service


class _FakeBox:
	def __init__(self, values):
		self.values = values

	def to_xyxy(self):
		return self.values


class _FakeCategory:
	def __init__(self, category_id):
		self.id = category_id


class _FakeDetection:
	def __init__(self, box, category_id):
		self.bbox = _FakeBox(box)
		self.category = _FakeCategory(category_id)


class MonitorServiceTests(unittest.TestCase):
	def setUp(self):
		self.original_seats = monitor_service.state["seats"]
		monitor_service.state["seats"] = []

	def tearDown(self):
		monitor_service.state["seats"] = self.original_seats

	def test_updates_existing_seat_identity_after_box_movement(self):
		first_detections = [
			_FakeDetection([10, 10, 40, 70], 0),
			_FakeDetection([100, 20, 140, 80], 1),
		]
		counter, matched, created = monitor_service.update_detected_seats(first_detections, 1)

		self.assertEqual((matched, created), (0, 2))
		self.assertEqual([seat["seat_id"] for seat in monitor_service.state["seats"]], [2, 3])

		second_detections = [
			_FakeDetection([103, 21, 143, 81], 2),
			_FakeDetection([12, 11, 42, 71], 3),
		]
		counter, matched, created = monitor_service.update_detected_seats(second_detections, counter)

		self.assertEqual((matched, created), (2, 0))
		seat_by_id = { seat["seat_id"]: seat for seat in monitor_service.state["seats"] }
		self.assertEqual(seat_by_id[2]["det_category"], 3)
		self.assertEqual(seat_by_id[3]["det_category"], 2)

	def test_parses_fenced_vlm_json(self):
		answer = monitor_service.parse_model_json(
			'```json\n{"status":"HEAD_DOWN","label":"疑似低头","confidence":0.6,"reason":"头部朝向桌面"}\n```'
		)

		self.assertEqual(answer["status"], "HEAD_DOWN")
		self.assertEqual(answer["confidence"], 0.6)

	def test_crop_bounds_stays_inside_frame(self):
		frame = np.zeros((100, 200, 3), dtype = np.uint8)

		self.assertEqual(monitor_service.crop_bounds(frame, [-20, -10, 250, 130], 10), (0, 0, 200, 100))
