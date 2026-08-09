import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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
		self.original_running = monitor_service.state["is_running"]
		self.original_runtime_id = monitor_service.persist_state["runtime_id"]
		self.original_detect_history = dict(monitor_service.detect_history)
		self.original_normal_streak = dict(monitor_service.normal_streak)
		self.original_alert_levels = dict(monitor_service.alert_level_map)
		self.original_pending = set(monitor_service.vlm_pending)
		self.original_review_times = dict(monitor_service.review_time_map)
		monitor_service.state["seats"] = []

	def tearDown(self):
		monitor_service.state["seats"] = self.original_seats
		monitor_service.state["is_running"] = self.original_running
		monitor_service.persist_state["runtime_id"] = self.original_runtime_id
		monitor_service.detect_history.clear()
		monitor_service.detect_history.update(self.original_detect_history)
		monitor_service.normal_streak.clear()
		monitor_service.normal_streak.update(self.original_normal_streak)
		monitor_service.alert_level_map.clear()
		monitor_service.alert_level_map.update(self.original_alert_levels)
		monitor_service.vlm_pending.clear()
		monitor_service.vlm_pending.update(self.original_pending)
		monitor_service.review_time_map.clear()
		monitor_service.review_time_map.update(self.original_review_times)

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

	def test_empty_detection_clears_seat_related_runtime_state(self):
		monitor_service.state["seats"] = [{ "seat_id": 7, "seat_code": "S07", "box": [1, 1, 2, 2] }]
		monitor_service.detect_history[7] = []
		monitor_service.normal_streak[7] = 2
		monitor_service.alert_level_map[7] = "警告"
		monitor_service.vlm_pending.add(7)
		monitor_service.review_time_map[7] = 1.0

		monitor_service.update_detected_seats([], 10)

		self.assertEqual(monitor_service.state["seats"], [])
		self.assertNotIn(7, monitor_service.detect_history)
		self.assertNotIn(7, monitor_service.normal_streak)
		self.assertNotIn(7, monitor_service.alert_level_map)
		self.assertNotIn(7, monitor_service.vlm_pending)
		self.assertNotIn(7, monitor_service.review_time_map)

	def test_stale_vlm_result_is_not_applied_to_new_runtime(self):
		monitor_service.state["is_running"] = True
		monitor_service.persist_state["runtime_id"] = "new-runtime"
		with patch.object(monitor_service, "apply_vlm_result") as apply_result:
			monitor_service.handle_review_result(("{}", {}, 1, 1), np.zeros((1, 1, 3)), "old-runtime")

		apply_result.assert_not_called()
