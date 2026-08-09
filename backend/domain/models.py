from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT as MYSQL_BIGINT
from sqlalchemy.dialects.mysql import JSON, LONGTEXT, TINYINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from core.database import Base


def uint_bigint():
	return BigInteger().with_variant(MYSQL_BIGINT(unsigned = True), "mysql")


class TimestampMixin:
	created_at = Column(DateTime, nullable = False, server_default = func.now())
	updated_at = Column(DateTime, nullable = False, server_default = func.now(), onupdate = func.now())


class SysUser(Base, TimestampMixin):
	__tablename__ = "sys_user"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	username = Column(String(64), nullable = False, unique = True)
	password_hash = Column(String(255), nullable = False)
	real_name = Column(String(64), nullable = False, default = "")
	phone = Column(String(32))
	email = Column(String(128))
	avatar_url = Column(String(255))
	status = Column(String(16), nullable = False, default = "ENABLED")
	failed_login_count = Column(Integer, nullable = False, default = 0)
	locked_until = Column(DateTime)
	last_login_at = Column(DateTime)
	last_login_ip = Column(String(64))
	password_changed_at = Column(DateTime)

	roles = relationship("SysUserRole", back_populates = "user")
	teacher = relationship("EduTeacher", back_populates = "user", uselist = False)


class SysRole(Base, TimestampMixin):
	__tablename__ = "sys_role"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	role_code = Column(String(32), nullable = False, unique = True)
	role_name = Column(String(64), nullable = False)
	description = Column(String(255))
	enabled = Column(TINYINT(1), nullable = False, default = 1)

	users = relationship("SysUserRole", back_populates = "role")


class SysUserRole(Base):
	__tablename__ = "sys_user_role"
	__table_args__ = (UniqueConstraint("user_id", "role_id", name = "uk_sys_user_role"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	user_id = Column(uint_bigint(), ForeignKey("sys_user.id"), nullable = False)
	role_id = Column(uint_bigint(), ForeignKey("sys_role.id"), nullable = False)
	created_at = Column(DateTime, nullable = False, server_default = func.now())

	user = relationship("SysUser", back_populates = "roles")
	role = relationship("SysRole", back_populates = "users")


class SysAuthToken(Base):
	__tablename__ = "sys_auth_token"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	user_id = Column(uint_bigint(), ForeignKey("sys_user.id"), nullable = False)
	token_jti = Column(String(128), nullable = False, unique = True)
	refresh_token_hash = Column(String(255))
	client_ip = Column(String(64))
	user_agent = Column(String(512))
	expires_at = Column(DateTime, nullable = False)
	revoked_at = Column(DateTime)
	created_at = Column(DateTime, nullable = False, server_default = func.now())


class SysLoginLog(Base):
	__tablename__ = "sys_login_log"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	user_id = Column(uint_bigint(), ForeignKey("sys_user.id"))
	username = Column(String(64), nullable = False)
	login_result = Column(String(16), nullable = False)
	fail_reason = Column(String(255))
	client_ip = Column(String(64))
	user_agent = Column(String(512))
	created_at = Column(DateTime, nullable = False, server_default = func.now())


class EduTeacher(Base, TimestampMixin):
	__tablename__ = "edu_teacher"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	user_id = Column(uint_bigint(), ForeignKey("sys_user.id"), unique = True)
	teacher_no = Column(String(64), nullable = False, unique = True)
	teacher_name = Column(String(64), nullable = False)
	gender = Column(String(16))
	phone = Column(String(32))
	email = Column(String(128))
	department = Column(String(128))
	title = Column(String(64))
	status = Column(String(16), nullable = False, default = "ENABLED")

	user = relationship("SysUser", back_populates = "teacher")
	classes = relationship("EduTeacherClass", back_populates = "teacher")


class EduClass(Base, TimestampMixin):
	__tablename__ = "edu_class"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	class_code = Column(String(64), nullable = False, unique = True)
	class_name = Column(String(64), nullable = False)
	grade_name = Column(String(64))
	academic_year = Column(String(32))
	head_teacher_id = Column(uint_bigint(), ForeignKey("edu_teacher.id"))
	default_video_path = Column(String(255))
	enabled = Column(TINYINT(1), nullable = False, default = 1)

	teacher_scopes = relationship("EduTeacherClass", back_populates = "edu_class")


class EduSubject(Base, TimestampMixin):
	__tablename__ = "edu_subject"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	subject_code = Column(String(64), nullable = False, unique = True)
	subject_name = Column(String(64), nullable = False)
	enabled = Column(TINYINT(1), nullable = False, default = 1)


class EduAcademicYear(Base, TimestampMixin):
	__tablename__ = "edu_academic_year"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	year_name = Column(String(32), nullable = False, unique = True)
	start_date = Column(Date, nullable = False)
	end_date = Column(Date, nullable = False)
	status = Column(String(16), nullable = False, default = "ENABLED")


class EduAcademicTerm(Base, TimestampMixin):
	__tablename__ = "edu_academic_term"
	__table_args__ = (UniqueConstraint("academic_year_id", "term_name", name = "uk_edu_academic_term_name"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	academic_year_id = Column(uint_bigint(), ForeignKey("edu_academic_year.id"), nullable = False)
	term_name = Column(String(64), nullable = False)
	start_date = Column(Date, nullable = False)
	end_date = Column(Date, nullable = False)
	status = Column(String(16), nullable = False, default = "ENABLED")


class TeachingCourse(Base, TimestampMixin):
	"""班级、学期和科目构成的连续教学课程，可在排课后再分配任课教师。"""
	__tablename__ = "teaching_course"
	__table_args__ = (UniqueConstraint("course_no", name = "uk_teaching_course_no"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	course_no = Column(String(64), nullable = False)
	term_id = Column(uint_bigint(), ForeignKey("edu_academic_term.id"), nullable = False)
	class_id = Column(uint_bigint(), ForeignKey("edu_class.id"), nullable = False)
	subject_id = Column(uint_bigint(), ForeignKey("edu_subject.id"), nullable = False)
	teacher_id = Column(uint_bigint(), ForeignKey("edu_teacher.id"), nullable = True)
	course_name = Column(String(128), nullable = False)
	planned_lesson_count = Column(Integer)
	start_date = Column(Date)
	end_date = Column(Date)
	status = Column(String(16), nullable = False, default = "DRAFT")

	term = relationship("EduAcademicTerm")
	edu_class = relationship("EduClass")
	subject = relationship("EduSubject")
	teacher = relationship("EduTeacher")


class EduLessonSchedule(Base, TimestampMixin):
	"""教学课程的固定周课表。weekday 使用 1 至 7 表示周一至周日。"""
	__tablename__ = "edu_lesson_schedule"
	__table_args__ = (UniqueConstraint("teaching_course_id", "weekday", "start_time", name = "uk_edu_lesson_schedule_time"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	teaching_course_id = Column(uint_bigint(), ForeignKey("teaching_course.id"), nullable = False)
	weekday = Column(Integer, nullable = False)
	start_time = Column(String(8), nullable = False)
	end_time = Column(String(8), nullable = False)
	lesson_title = Column(String(128))
	enabled = Column(TINYINT(1), nullable = False, default = 1)


class CameraDevice(Base, TimestampMixin):
	__tablename__ = "camera_device"
	__table_args__ = (UniqueConstraint("device_code", name = "uk_camera_device_code"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	device_code = Column(String(64), nullable = False)
	device_name = Column(String(128), nullable = False)
	location = Column(String(255))
	source_path = Column(String(255))
	enabled = Column(TINYINT(1), nullable = False, default = 1)
	remark = Column(String(500))


class CameraClassBinding(Base, TimestampMixin):
	__tablename__ = "camera_class_binding"
	__table_args__ = (UniqueConstraint("camera_id", "class_id", "effective_start_date", name = "uk_camera_class_binding_start"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	camera_id = Column(uint_bigint(), ForeignKey("camera_device.id"), nullable = False)
	class_id = Column(uint_bigint(), ForeignKey("edu_class.id"), nullable = False)
	effective_start_date = Column(Date, nullable = False)
	effective_end_date = Column(Date)
	enabled = Column(TINYINT(1), nullable = False, default = 1)
	remark = Column(String(500))


class EduTeacherClass(Base):
	__tablename__ = "edu_teacher_class"
	__table_args__ = (UniqueConstraint("teacher_id", "class_id", "subject_id", "relation_type", name = "uk_edu_teacher_class_scope"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	teacher_id = Column(uint_bigint(), ForeignKey("edu_teacher.id"), nullable = False)
	class_id = Column(uint_bigint(), ForeignKey("edu_class.id"), nullable = False)
	subject_id = Column(uint_bigint(), ForeignKey("edu_subject.id"))
	relation_type = Column(String(32), nullable = False)
	can_view_monitor = Column(TINYINT(1), nullable = False, default = 1)
	can_start_monitor = Column(TINYINT(1), nullable = False, default = 0)
	can_review = Column(TINYINT(1), nullable = False, default = 1)
	start_date = Column(Date)
	end_date = Column(Date)
	enabled = Column(TINYINT(1), nullable = False, default = 1)
	created_at = Column(DateTime, nullable = False, server_default = func.now())

	teacher = relationship("EduTeacher", back_populates = "classes")
	edu_class = relationship("EduClass", back_populates = "teacher_scopes")
	subject = relationship("EduSubject")


class MonitorSession(Base, TimestampMixin):
	__tablename__ = "monitor_session"
	__table_args__ = (
		# 计划课次由课表与计划开始时间唯一确定，手工演示课次的 NULL 值不受影响。
		UniqueConstraint("schedule_id", "planned_started_at", name = "uk_monitor_session_schedule_start"),
	)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	session_no = Column(String(64), nullable = False, unique = True)
	class_id = Column(uint_bigint(), ForeignKey("edu_class.id"), nullable = False)
	class_name = Column(String(64), nullable = False)
	teacher_id = Column(uint_bigint(), ForeignKey("edu_teacher.id"))
	teacher_name = Column(String(64))
	subject_id = Column(uint_bigint(), ForeignKey("edu_subject.id"))
	subject_name = Column(String(64))
	lesson_title = Column(String(128))
	term_id = Column(uint_bigint(), ForeignKey("edu_academic_term.id"))
	teaching_course_id = Column(uint_bigint(), ForeignKey("teaching_course.id"))
	schedule_id = Column(uint_bigint(), ForeignKey("edu_lesson_schedule.id"))
	camera_id = Column(uint_bigint(), ForeignKey("camera_device.id"))
	camera_binding_id = Column(uint_bigint(), ForeignKey("camera_class_binding.id"))
	operator_user_id = Column(uint_bigint(), ForeignKey("sys_user.id"))
	operator_name = Column(String(64))
	video_path = Column(String(255))
	img_width = Column(Integer)
	img_height = Column(Integer)
	status = Column(String(16), nullable = False, default = "RUNNING")
	analysis_status = Column(String(16), nullable = False, default = "PENDING")
	planned_started_at = Column(DateTime)
	planned_ended_at = Column(DateTime)
	analysis_completed_at = Column(DateTime)
	started_at = Column(DateTime, nullable = False, server_default = func.now())
	ended_at = Column(DateTime)
	last_heartbeat_at = Column(DateTime)
	total_seat_count = Column(Integer, nullable = False, default = 0)
	warning_count = Column(Integer, nullable = False, default = 0)
	notice_count = Column(Integer, nullable = False, default = 0)
	event_count = Column(Integer, nullable = False, default = 0)
	detect_config_json = Column(JSON)
	vlm_config_json = Column(JSON)
	rule_config_json = Column(JSON)


class MonitorSessionSeat(Base):
	__tablename__ = "monitor_session_seat"
	__table_args__ = (UniqueConstraint("session_id", "runtime_seat_id", name = "uk_monitor_session_runtime_seat"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"), nullable = False)
	runtime_seat_id = Column(Integer, nullable = False)
	seat_code = Column(String(32), nullable = False)
	box_x1 = Column(DECIMAL(10, 2), nullable = False)
	box_y1 = Column(DECIMAL(10, 2), nullable = False)
	box_x2 = Column(DECIMAL(10, 2), nullable = False)
	box_y2 = Column(DECIMAL(10, 2), nullable = False)
	status = Column(String(32), nullable = False, default = "NORMAL")
	det_category = Column(Integer)
	analysis_source = Column(String(32))
	locked_abnormal = Column(TINYINT(1), nullable = False, default = 0)
	first_seen_at = Column(DateTime, nullable = False, server_default = func.now())
	last_seen_at = Column(DateTime, nullable = False, server_default = func.now())


class MonitorBehaviorEvent(Base, TimestampMixin):
	__tablename__ = "monitor_behavior_event"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	event_uid = Column(String(64), nullable = False, unique = True)
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"), nullable = False)
	analysis_run_id = Column(uint_bigint(), ForeignKey("lesson_analysis_run.id"))
	class_id = Column(uint_bigint(), ForeignKey("edu_class.id"), nullable = False)
	seat_id = Column(uint_bigint(), ForeignKey("monitor_session_seat.id"))
	seat_code = Column(String(32), nullable = False)
	level = Column(String(16), nullable = False)
	status = Column(String(32), nullable = False)
	label = Column(String(128), nullable = False, default = "")
	reason = Column(Text)
	source = Column(String(32), nullable = False, default = "DETECT")
	analysis_source = Column(String(32), nullable = False, default = "DETECT")
	image_url = Column(String(255))
	image_path = Column(String(255))
	box_x1 = Column(DECIMAL(10, 2))
	box_y1 = Column(DECIMAL(10, 2))
	box_x2 = Column(DECIMAL(10, 2))
	box_y2 = Column(DECIMAL(10, 2))
	event_time = Column(DateTime, nullable = False)
	confirmed_by_vlm = Column(TINYINT(1), nullable = False, default = 0)
	handle_status = Column(String(32), nullable = False, default = "UNHANDLED")
	handled_by = Column(uint_bigint(), ForeignKey("sys_user.id"))
	handled_at = Column(DateTime)
	handle_remark = Column(String(500))


class MonitorEventFrame(Base):
	__tablename__ = "monitor_event_frame"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	event_id = Column(uint_bigint(), ForeignKey("monitor_behavior_event.id"), nullable = False)
	frame_index = Column(Integer, nullable = False, default = 0)
	frame_time = Column(DateTime)
	focus_image_url = Column(String(255))
	focus_image_path = Column(String(255))
	seat_code = Column(String(32))
	status = Column(String(32))
	status_text = Column(String(64))
	ratio = Column(DECIMAL(10, 4))
	box_conf = Column(DECIMAL(10, 4))
	box_x1 = Column(DECIMAL(10, 2))
	box_y1 = Column(DECIMAL(10, 2))
	box_x2 = Column(DECIMAL(10, 2))
	box_y2 = Column(DECIMAL(10, 2))
	raw_payload_json = Column(JSON)
	created_at = Column(DateTime, nullable = False, server_default = func.now())


class MonitorVlmReview(Base):
	__tablename__ = "monitor_vlm_review"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	event_id = Column(uint_bigint(), ForeignKey("monitor_behavior_event.id"))
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"), nullable = False)
	seat_id = Column(uint_bigint(), ForeignKey("monitor_session_seat.id"))
	model_name = Column(String(64), nullable = False, default = "qwen-vl-max")
	request_image_url = Column(String(255))
	request_image_path = Column(String(255))
	raw_response = Column(LONGTEXT)
	parsed_status = Column(String(32))
	parsed_label = Column(String(128))
	parsed_reason = Column(Text)
	success = Column(TINYINT(1), nullable = False, default = 1)
	error_message = Column(Text)
	latency_ms = Column(Integer)
	created_at = Column(DateTime, nullable = False, server_default = func.now())


class MonitorTeachingReview(Base, TimestampMixin):
	__tablename__ = "monitor_teaching_review"
	__table_args__ = (UniqueConstraint("session_id", "teacher_id", name = "uk_monitor_teaching_review_teacher"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"), nullable = False)
	teacher_id = Column(uint_bigint(), ForeignKey("edu_teacher.id"), nullable = False)
	review_status = Column(String(16), nullable = False, default = "PENDING")
	teaching_effect_score = Column(DECIMAL(5, 2))
	focus_summary = Column(Text)
	problem_summary = Column(Text)
	improvement_plan = Column(Text)
	reviewed_at = Column(DateTime)


class LessonAnalysisRun(Base, TimestampMixin):
	__tablename__ = "lesson_analysis_run"
	__table_args__ = (UniqueConstraint("session_id", "run_no", name = "uk_lesson_analysis_run_no"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"), nullable = False)
	run_no = Column(Integer, nullable = False)
	run_status = Column(String(16), nullable = False, default = "PENDING")
	is_current = Column(TINYINT(1), nullable = False, default = 0)
	model_name = Column(String(128))
	model_version = Column(String(128))
	rule_version = Column(String(64))
	config_json = Column(JSON)
	started_at = Column(DateTime)
	finished_at = Column(DateTime)
	error_message = Column(Text)


class LessonAnalysisSummary(Base, TimestampMixin):
	__tablename__ = "lesson_analysis_summary"
	__table_args__ = (UniqueConstraint("analysis_run_id", name = "uk_lesson_analysis_summary_run"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	analysis_run_id = Column(uint_bigint(), ForeignKey("lesson_analysis_run.id"), nullable = False)
	planned_duration_seconds = Column(Integer, nullable = False, default = 0)
	valid_analysis_seconds = Column(Integer, nullable = False, default = 0)
	sampled_frame_count = Column(Integer, nullable = False, default = 0)
	valid_frame_count = Column(Integer, nullable = False, default = 0)
	avg_detected_seat_count = Column(DECIMAL(10, 2))
	event_count = Column(Integer, nullable = False, default = 0)
	confirmed_event_count = Column(Integer, nullable = False, default = 0)
	data_quality_level = Column(String(16), nullable = False, default = "LIMITED")
	quality_remark = Column(Text)
	generated_at = Column(DateTime, nullable = False, server_default = func.now())


class LessonBehaviorStat(Base, TimestampMixin):
	__tablename__ = "lesson_behavior_stat"
	__table_args__ = (UniqueConstraint("summary_id", "behavior_code", name = "uk_lesson_behavior_stat"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	summary_id = Column(uint_bigint(), ForeignKey("lesson_analysis_summary.id"), nullable = False)
	behavior_code = Column(String(32), nullable = False)
	segment_count = Column(Integer, nullable = False, default = 0)
	event_count = Column(Integer, nullable = False, default = 0)
	total_duration_seconds = Column(Integer, nullable = False, default = 0)
	duration_ratio = Column(DECIMAL(10, 4), nullable = False, default = 0)
	vlm_confirmed_count = Column(Integer, nullable = False, default = 0)


class CourseAnalysisAggregate(Base, TimestampMixin):
	__tablename__ = "course_analysis_aggregate"
	__table_args__ = (UniqueConstraint("teaching_course_id", "scope_type", "period_start_date", "period_end_date", "calculation_version", name = "uk_course_analysis_aggregate"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	aggregate_no = Column(String(64), nullable = False, unique = True)
	teaching_course_id = Column(uint_bigint(), ForeignKey("teaching_course.id"), nullable = False)
	scope_type = Column(String(16), nullable = False)
	period_start_date = Column(Date, nullable = False)
	period_end_date = Column(Date, nullable = False)
	source_session_count = Column(Integer, nullable = False, default = 0)
	completed_session_count = Column(Integer, nullable = False, default = 0)
	valid_analysis_seconds = Column(Integer, nullable = False, default = 0)
	data_quality_level = Column(String(16), nullable = False, default = "LIMITED")
	calculation_version = Column(Integer, nullable = False, default = 1)
	aggregate_status = Column(String(16), nullable = False, default = "DRAFT")
	calculated_at = Column(DateTime)


class CourseBehaviorStat(Base, TimestampMixin):
	__tablename__ = "course_behavior_stat"
	__table_args__ = (UniqueConstraint("aggregate_id", "behavior_code", name = "uk_course_behavior_stat"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	aggregate_id = Column(uint_bigint(), ForeignKey("course_analysis_aggregate.id"), nullable = False)
	behavior_code = Column(String(32), nullable = False)
	segment_count = Column(Integer, nullable = False, default = 0)
	event_count = Column(Integer, nullable = False, default = 0)
	total_duration_seconds = Column(Integer, nullable = False, default = 0)
	average_per_session = Column(DECIMAL(10, 4), nullable = False, default = 0)
	average_duration_ratio = Column(DECIMAL(10, 4), nullable = False, default = 0)
	session_coverage_count = Column(Integer, nullable = False, default = 0)


class CourseAggregateSource(Base):
	__tablename__ = "course_aggregate_source"
	__table_args__ = (UniqueConstraint("aggregate_id", "summary_id", name = "uk_course_aggregate_source"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	aggregate_id = Column(uint_bigint(), ForeignKey("course_analysis_aggregate.id"), nullable = False)
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"), nullable = False)
	analysis_run_id = Column(uint_bigint(), ForeignKey("lesson_analysis_run.id"), nullable = False)
	summary_id = Column(uint_bigint(), ForeignKey("lesson_analysis_summary.id"), nullable = False)
	included_at = Column(DateTime, nullable = False, server_default = func.now())


class TeachingAnalysisReport(Base, TimestampMixin):
	__tablename__ = "teaching_analysis_report"
	__table_args__ = (UniqueConstraint("report_no", name = "uk_teaching_analysis_report_no"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	report_no = Column(String(64), nullable = False)
	report_title = Column(String(255), nullable = False)
	report_scope = Column(String(16), nullable = False)
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"))
	aggregate_id = Column(uint_bigint(), ForeignKey("course_analysis_aggregate.id"))
	teaching_course_id = Column(uint_bigint(), ForeignKey("teaching_course.id"))
	report_version = Column(Integer, nullable = False, default = 1)
	report_status = Column(String(16), nullable = False, default = "DRAFT")
	generated_mode = Column(String(32), nullable = False, default = "SYSTEM")
	overview_text = Column(Text)
	finding_text = Column(Text)
	suggestion_text = Column(Text)
	teacher_conclusion = Column(Text)
	data_snapshot_json = Column(JSON)
	export_file_path = Column(String(255))
	generated_by = Column(uint_bigint(), ForeignKey("sys_user.id"))
	published_by = Column(uint_bigint(), ForeignKey("sys_user.id"))
	published_at = Column(DateTime)


class CourseAnalysisEntry(Base, TimestampMixin):
	__tablename__ = "course_analysis_entry"
	__table_args__ = (UniqueConstraint("teaching_course_id", "session_id", name = "uk_course_analysis_entry_session"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	teaching_course_id = Column(uint_bigint(), ForeignKey("teaching_course.id"), nullable = False)
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"), nullable = False)
	analysis_run_id = Column(uint_bigint(), ForeignKey("lesson_analysis_run.id"), nullable = False)
	summary_id = Column(uint_bigint(), ForeignKey("lesson_analysis_summary.id"), nullable = False)
	report_id = Column(uint_bigint(), ForeignKey("teaching_analysis_report.id"))
	lesson_index = Column(Integer, nullable = False, default = 0)
	lesson_date = Column(Date, nullable = False)
	lesson_title = Column(String(128))
	comparison_base_entry_id = Column(uint_bigint(), ForeignKey("course_analysis_entry.id"))
	system_change_summary = Column(Text)
	teacher_change_note = Column(Text)
	is_baseline = Column(TINYINT(1), nullable = False, default = 0)
	is_milestone = Column(TINYINT(1), nullable = False, default = 0)


class TeachingImprovementAction(Base, TimestampMixin):
	__tablename__ = "teaching_improvement_action"

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	teaching_course_id = Column(uint_bigint(), ForeignKey("teaching_course.id"), nullable = False)
	source_entry_id = Column(uint_bigint(), ForeignKey("course_analysis_entry.id"), nullable = False)
	issue_type = Column(String(64))
	issue_description = Column(Text, nullable = False)
	improvement_plan = Column(Text, nullable = False)
	planned_for_entry_id = Column(uint_bigint(), ForeignKey("course_analysis_entry.id"))
	action_status = Column(String(16), nullable = False, default = "PLANNED")
	implemented_at = Column(DateTime)
	verified_by_entry_id = Column(uint_bigint(), ForeignKey("course_analysis_entry.id"))
	verification_note = Column(Text)
	created_by = Column(uint_bigint(), ForeignKey("edu_teacher.id"), nullable = False)
	verified_at = Column(DateTime)


class TeachingReportEvidence(Base, TimestampMixin):
	__tablename__ = "teaching_report_evidence"
	__table_args__ = (UniqueConstraint("report_id", "event_id", "evidence_type", name = "uk_teaching_report_evidence"),)

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	report_id = Column(uint_bigint(), ForeignKey("teaching_analysis_report.id"), nullable = False)
	session_id = Column(uint_bigint(), ForeignKey("monitor_session.id"), nullable = False)
	event_id = Column(uint_bigint(), ForeignKey("monitor_behavior_event.id"))
	evidence_type = Column(String(32), nullable = False)
	sort_no = Column(Integer, nullable = False, default = 0)
	remark = Column(Text)
