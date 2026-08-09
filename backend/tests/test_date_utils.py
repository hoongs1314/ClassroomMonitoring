import sys
import unittest
from datetime import datetime
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
	sys.path.insert(0, str(BACKEND_DIR))

from core.date_utils import parse_date_range


class DateUtilsTests(unittest.TestCase):
	def test_parses_inclusive_calendar_date_range(self):
		start_at, end_at = parse_date_range("2026-08-06", "2026-08-06")

		self.assertEqual(start_at, datetime(2026, 8, 6, 0, 0, 0))
		self.assertEqual(end_at, datetime(2026, 8, 7, 0, 0, 0))

	def test_supports_one_sided_date_range(self):
		start_at, end_at = parse_date_range("2026-08-01", None)

		self.assertEqual(start_at, datetime(2026, 8, 1, 0, 0, 0))
		self.assertIsNone(end_at)

	def test_rejects_invalid_date_format(self):
		with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
			parse_date_range("2026/08/06", None)

	def test_rejects_reversed_date_range(self):
		with self.assertRaisesRegex(ValueError, "结束日期"):
			parse_date_range("2026-08-07", "2026-08-06")
