"""按固定课表创建课次并生成待处理的课后分析运行。"""

import logging
import time
from datetime import datetime, time as clock_time
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from core.database import db_session
from domain.models import (
	CameraClassBinding,
	CameraDevice,
	EduAcademicTerm,
	EduLessonSchedule,
	LessonAnalysisRun,
	MonitorSession,
	TeachingCourse,
)


logger = logging.getLogger("monitor.schedule")
SCHEDULE_SYNC_SECONDS = 30


def _parse_clock(value):
	return datetime.strptime(value, "%H:%M").time()


def _session_no():
	return f"LS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid4().hex[:8]}"


def _resolve_binding(db, class_id, target_date):
	return (
		db.query(CameraClassBinding)
		.filter(
			CameraClassBinding.class_id == class_id,
			CameraClassBinding.enabled == 1,
			CameraClassBinding.effective_start_date <= target_date,
			or_(CameraClassBinding.effective_end_date.is_(None), CameraClassBinding.effective_end_date > target_date),
		)
		.order_by(CameraClassBinding.effective_start_date.desc())
		.first()
	)


def synchronize_scheduled_sessions(now = None):
	"""同步当前时段课次。

	课表按中国校园作息的本地时钟维护，当前项目尚未引入时区配置，因此使用本机本地时间。
	只创建课次和待分析记录；实际视频分析由独立分析 Worker 完成。
	"""
	now = now or datetime.now()
	created = 0
	ended = 0
	with db_session() as db:
		active_schedules = (
			db.query(EduLessonSchedule, TeachingCourse, EduAcademicTerm)
			.join(TeachingCourse, TeachingCourse.id == EduLessonSchedule.teaching_course_id)
			.join(EduAcademicTerm, EduAcademicTerm.id == TeachingCourse.term_id)
			.filter(
				EduLessonSchedule.enabled == 1,
				TeachingCourse.status == "ACTIVE",
				EduAcademicTerm.status == "ENABLED",
				EduAcademicTerm.start_date <= now.date(),
				EduAcademicTerm.end_date >= now.date(),
			)
			.all()
		)
		for schedule, course, term in active_schedules:
			if schedule.weekday != now.isoweekday():
				continue
			# 未分配任课教师的课程仅用于教务排课展示，不能自动生成归属不明的监控课次。
			if course.teacher_id is None:
				continue
			if course.start_date and now.date() < course.start_date:
				continue
			if course.end_date and now.date() > course.end_date:
				continue
			start_at = datetime.combine(now.date(), _parse_clock(schedule.start_time))
			end_at = datetime.combine(now.date(), _parse_clock(schedule.end_time))
			if not (start_at <= now < end_at):
				continue
			exists = (
				db.query(MonitorSession)
				.filter(MonitorSession.schedule_id == schedule.id, MonitorSession.planned_started_at == start_at)
				.first()
			)
			if exists:
				continue
			binding = _resolve_binding(db, course.class_id, now.date())
			if not binding:
				logger.warning("[Schedule] 跳过课表%s：班级%d没有有效摄像头绑定", schedule.id, course.class_id)
				continue
			camera = db.query(CameraDevice).filter(CameraDevice.id == binding.camera_id, CameraDevice.enabled == 1).first()
			if not camera:
				logger.warning("[Schedule] 跳过课表%s：摄像设备不可用", schedule.id)
				continue
			teacher = course.teacher
			cls = course.edu_class
			subject = course.subject
			session = MonitorSession(
				session_no = _session_no(),
				class_id = course.class_id,
				class_name = cls.class_name,
				teacher_id = course.teacher_id,
				teacher_name = teacher.teacher_name,
				subject_id = course.subject_id,
				subject_name = subject.subject_name,
				lesson_title = schedule.lesson_title,
				term_id = course.term_id,
				teaching_course_id = course.id,
				schedule_id = schedule.id,
				camera_id = camera.id,
				camera_binding_id = binding.id,
				video_path = camera.source_path,
				# 仅表示课表已生成，不把尚未接入离线处理器的课次伪装成正在推理。
				status = "SCHEDULED",
				analysis_status = "PENDING",
				planned_started_at = start_at,
				planned_ended_at = end_at,
				started_at = start_at,
				last_heartbeat_at = now,
			)
			# 应用层预检查无法抵御多实例竞态；数据库唯一约束为最终边界。
			try:
				with db.begin_nested():
					db.add(session)
					db.flush()
			except IntegrityError:
				logger.info("[Schedule] 课表%s的计划课次已由其他实例创建", schedule.id)
				continue
			created += 1

		# 已结束的计划课次转为待分析。此处不伪造分析结论，Worker 完成推理后再生成汇总和报告。
		ended_sessions = (
			db.query(MonitorSession)
			.filter(
				MonitorSession.status == "SCHEDULED",
				MonitorSession.schedule_id.isnot(None),
				MonitorSession.planned_ended_at <= now,
			)
			.all()
		)
		for session in ended_sessions:
			session.status = "STOPPED"
			session.ended_at = session.planned_ended_at
			session.last_heartbeat_at = now
			if not db.query(LessonAnalysisRun).filter(LessonAnalysisRun.session_id == session.id).first():
				db.add(
					LessonAnalysisRun(
						session_id = session.id,
						run_no = 1,
						run_status = "PENDING",
						is_current = 1,
						model_name = "yolo-sahi-vlm",
						rule_version = "post-class-v1",
					)
				)
			ended += 1
	return { "created": created, "ended": ended }


def schedule_worker_loop():
	"""轻量调度循环，避免引入额外队列依赖。"""
	while True:
		try:
			result = synchronize_scheduled_sessions()
			if result["created"] or result["ended"]:
				logger.info("[Schedule] 同步完成: 创建%d个课次，结束%d个课次", result["created"], result["ended"])
		except Exception as exc:
			logger.exception("[Schedule] 同步失败: %s", exc)
		time.sleep(SCHEDULE_SYNC_SECONDS)
