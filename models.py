from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT as MYSQL_BIGINT
from sqlalchemy.dialects.mysql import JSON, LONGTEXT, TINYINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


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

	id = Column(uint_bigint(), primary_key = True, autoincrement = True)
	session_no = Column(String(64), nullable = False, unique = True)
	class_id = Column(uint_bigint(), ForeignKey("edu_class.id"), nullable = False)
	class_name = Column(String(64), nullable = False)
	teacher_id = Column(uint_bigint(), ForeignKey("edu_teacher.id"))
	teacher_name = Column(String(64))
	subject_id = Column(uint_bigint(), ForeignKey("edu_subject.id"))
	subject_name = Column(String(64))
	lesson_title = Column(String(128))
	operator_user_id = Column(uint_bigint(), ForeignKey("sys_user.id"))
	operator_name = Column(String(64))
	video_path = Column(String(255))
	img_width = Column(Integer)
	img_height = Column(Integer)
	status = Column(String(16), nullable = False, default = "RUNNING")
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
