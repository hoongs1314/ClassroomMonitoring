import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from inspect import signature
from pathlib import Path

from fastapi import HTTPException


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
	sys.path.insert(0, str(BACKEND_DIR))

from domain.models import (
	CameraClassBinding,
	CameraDevice,
	CourseAnalysisAggregate,
	CourseAnalysisEntry,
	EduClass,
	EduAcademicTerm,
	EduAcademicYear,
	EduLessonSchedule,
	EduSubject,
	EduTeacher,
	LessonAnalysisRun,
	LessonAnalysisSummary,
	TeachingAnalysisReport,
	TeachingCourse,
	TeachingImprovementAction,
)
from services.schedule_service import _parse_clock
from services.teaching_analysis_service import _duration_seconds
from routers.course_analysis_routes import _is_schedule_current, _serialize_course
from routers.teacher_routes import _review_score, teacher_sessions


class TeachingAnalysisContractTests(unittest.TestCase):
	def test_post_class_entities_are_registered(self):
		models = [
			EduAcademicYear,
			EduAcademicTerm,
			TeachingCourse,
			EduLessonSchedule,
			CameraDevice,
			CameraClassBinding,
			LessonAnalysisRun,
			LessonAnalysisSummary,
			CourseAnalysisAggregate,
			CourseAnalysisEntry,
			TeachingAnalysisReport,
			TeachingImprovementAction,
		]
		self.assertEqual(
			{model.__tablename__ for model in models},
			{
				"edu_academic_year",
				"edu_academic_term",
				"teaching_course",
				"edu_lesson_schedule",
				"camera_device",
				"camera_class_binding",
				"lesson_analysis_run",
				"lesson_analysis_summary",
				"course_analysis_aggregate",
				"course_analysis_entry",
				"teaching_analysis_report",
				"teaching_improvement_action",
			},
		)

	def test_schedule_clock_requires_hour_and_minute(self):
		self.assertEqual(_parse_clock("08:00").strftime("%H:%M"), "08:00")
		with self.assertRaises(ValueError):
			_parse_clock("上午八点")

	def test_teacher_course_payload_includes_academic_year(self):
		year = EduAcademicYear(id = 1, year_name = "2026-2027")
		term = EduAcademicTerm(id = 2, academic_year_id = year.id, term_name = "第一学期")
		cls = EduClass(id = 3, class_name = "高三（1）班")
		subject = EduSubject(id = 4, subject_name = "数学")
		teacher = EduTeacher(id = 5, teacher_name = "李老师")
		course = TeachingCourse(id = 6, term_id = term.id, class_id = cls.id, subject_id = subject.id, teacher_id = teacher.id, course_name = "高三数学")

		payload = _serialize_course(course, { year.id: year }, { term.id: term }, { cls.id: cls }, { subject.id: subject }, { teacher.id: teacher })

		self.assertEqual(payload["academic_year_name"], "2026-2027")
		self.assertEqual(payload["class_name"], "高三（1）班")

	def test_teaching_course_allows_assignment_after_schedule_setup(self):
		year = EduAcademicYear(id = 1, year_name = "2026-2027")
		term = EduAcademicTerm(id = 2, academic_year_id = year.id, term_name = "第一学期")
		cls = EduClass(id = 3, class_name = "高三（1）班")
		subject = EduSubject(id = 4, subject_name = "数学")
		course = TeachingCourse(id = 6, term_id = term.id, class_id = cls.id, subject_id = subject.id, teacher_id = None, course_name = "高三数学")

		payload = _serialize_course(course, { year.id: year }, { term.id: term }, { cls.id: cls }, { subject.id: subject }, {})

		self.assertTrue(TeachingCourse.__table__.c.teacher_id.nullable)
		self.assertIsNone(payload["teacher_id"])
		self.assertEqual(payload["teacher_name"], "")

	def test_current_course_requires_matching_date_weekday_and_schedule_time(self):
		term = EduAcademicTerm(
			id = 2,
			academic_year_id = 1,
			term_name = "第一学期",
			start_date = date(2026, 9, 1),
			end_date = date(2027, 1, 31),
			status = "ENABLED",
		)
		course = TeachingCourse(id = 6, term_id = term.id, class_id = 3, subject_id = 4, teacher_id = 5, course_name = "高三数学", status = "ACTIVE")
		schedule = EduLessonSchedule(teaching_course_id = course.id, weekday = 1, start_time = "08:00", end_time = "08:45", enabled = 1)

		self.assertTrue(_is_schedule_current(course, term, schedule, datetime(2026, 9, 7, 8, 20)))
		self.assertFalse(_is_schedule_current(course, term, schedule, datetime(2026, 9, 7, 8, 45)))
		self.assertFalse(_is_schedule_current(course, term, schedule, datetime(2026, 9, 8, 8, 20)))

	def test_course_archive_request_uses_teaching_course_scope(self):
		parameter = signature(teacher_sessions).parameters["x_teaching_course_id"]
		self.assertEqual(parameter.default.alias, "X-Teaching-Course-Id")

	def test_effective_duration_does_not_accept_negative_time_range(self):
		started_at = datetime(2026, 9, 1, 8, 0, 0)
		self.assertEqual(_duration_seconds(started_at, datetime(2026, 9, 1, 8, 45, 0)), 2700)
		self.assertEqual(_duration_seconds(started_at, datetime(2026, 9, 1, 7, 59, 59)), 0)

	def test_review_score_is_limited_to_valid_range(self):
		self.assertEqual(_review_score({ "teaching_effect_score": "88.5" }), Decimal("88.5"))
		with self.assertRaises(HTTPException):
			_review_score({ "teaching_effect_score": "101" })
