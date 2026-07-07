from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_context, is_admin, parse_header_int
from domain.models import EduClass, EduSubject, EduTeacher, EduTeacherClass, MonitorBehaviorEvent, MonitorEventFrame, MonitorSession, MonitorTeachingReview


router = APIRouter(prefix = "/api/teacher", tags = ["teacher"])


def _allowed_class_ids(db, context):
	if is_admin(context):
		return None
	teacher = context.get("teacher")
	if not teacher:
		return []
	rows = (
		db.query(EduTeacherClass.class_id)
		.filter(
			EduTeacherClass.teacher_id == teacher.id,
			EduTeacherClass.enabled == 1,
			EduTeacherClass.can_view_monitor == 1,
		)
		.distinct()
		.all()
	)
	return [row[0] for row in rows]


def _ensure_session_access(db, context, session_id):
	session = db.query(MonitorSession).filter(MonitorSession.id == session_id).first()
	if not session:
		raise HTTPException(status_code = 404, detail = "监控记录不存在")
	allowed = _allowed_class_ids(db, context)
	if allowed is not None and session.class_id not in allowed:
		raise HTTPException(status_code = 403, detail = "无权访问该班级监控记录")
	return session


def _ensure_review_teacher(db, context, session, teacher_id = None):
	if is_admin(context):
		if teacher_id:
			teacher = db.query(EduTeacher).filter(EduTeacher.id == teacher_id).first()
			if teacher:
				return teacher
		teacher = context.get("teacher")
		if teacher:
			return teacher
		raise HTTPException(status_code = 400, detail = "管理员提交复盘时需要提供 X-Teacher-Id")

	teacher = context.get("teacher")
	if not teacher:
		raise HTTPException(status_code = 403, detail = "当前账号未绑定教师档案")
	scope = (
		db.query(EduTeacherClass)
		.filter(
			EduTeacherClass.teacher_id == teacher.id,
			EduTeacherClass.class_id == session.class_id,
			EduTeacherClass.enabled == 1,
			EduTeacherClass.can_review == 1,
		)
		.first()
	)
	if not scope:
		raise HTTPException(status_code = 403, detail = "无权复盘该班级监控记录")
	return teacher


@router.get("/classes")
def teacher_classes(context = Depends(get_current_context), db: Session = Depends(get_db)):
	allowed = _allowed_class_ids(db, context)
	query = db.query(EduClass).filter(EduClass.enabled == 1)
	if allowed is not None:
		if not allowed:
			return { "ok": True, "classes": [] }
		query = query.filter(EduClass.id.in_(allowed))
	rows = query.order_by(EduClass.class_code.asc()).all()
	return {
		"ok": True,
		"classes": [
			{
				"id": row.id,
				"class_code": row.class_code,
				"class_name": row.class_name,
				"grade_name": row.grade_name,
				"academic_year": row.academic_year,
				"default_video_path": row.default_video_path,
			}
			for row in rows
		],
	}


@router.get("/subjects")
def subjects(context = Depends(get_current_context), db: Session = Depends(get_db)):
	rows = db.query(EduSubject).filter(EduSubject.enabled == 1).order_by(EduSubject.subject_code.asc()).all()
	return { "ok": True, "subjects": [{"id": row.id, "subject_code": row.subject_code, "subject_name": row.subject_name} for row in rows] }


@router.get("/sessions")
def teacher_sessions(
	x_class_id = Header(default = None, alias = "X-Class-Id"),
	x_page_no = Header(default = "1", alias = "X-Page-No"),
	x_page_size = Header(default = "20", alias = "X-Page-Size"),
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	class_id = parse_header_int(x_class_id, "X-Class-Id")
	page_no = max(parse_header_int(x_page_no, "X-Page-No") or 1, 1)
	page_size = min(max(parse_header_int(x_page_size, "X-Page-Size") or 20, 1), 100)
	allowed = _allowed_class_ids(db, context)
	query = db.query(MonitorSession)
	if allowed is not None:
		if not allowed:
			return { "ok": True, "total": 0, "items": [] }
		query = query.filter(MonitorSession.class_id.in_(allowed))
	if class_id:
		if allowed is not None and class_id not in allowed:
			raise HTTPException(status_code = 403, detail = "无权访问该班级")
		query = query.filter(MonitorSession.class_id == class_id)
	total = query.count()
	rows = query.order_by(MonitorSession.started_at.desc()).offset((page_no - 1) * page_size).limit(page_size).all()
	return {
		"ok": True,
		"total": total,
		"items": [
			{
				"id": row.id,
				"session_no": row.session_no,
				"class_id": row.class_id,
				"class_name": row.class_name,
				"teacher_name": row.teacher_name,
				"subject_name": row.subject_name,
				"lesson_title": row.lesson_title,
				"status": row.status,
				"started_at": row.started_at,
				"ended_at": row.ended_at,
				"total_seat_count": row.total_seat_count,
				"warning_count": row.warning_count,
				"notice_count": row.notice_count,
				"event_count": row.event_count,
			}
			for row in rows
		],
	}


@router.get("/session/detail")
def session_detail(
	x_session_id = Header(default = None, alias = "X-Session-Id"),
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	session_id = parse_header_int(x_session_id, "X-Session-Id", required = True)
	session = _ensure_session_access(db, context, session_id)
	return {
		"ok": True,
		"session": {
			"id": session.id,
			"session_no": session.session_no,
			"class_id": session.class_id,
			"class_name": session.class_name,
			"teacher_name": session.teacher_name,
			"subject_name": session.subject_name,
			"lesson_title": session.lesson_title,
			"status": session.status,
			"started_at": session.started_at,
			"ended_at": session.ended_at,
			"total_seat_count": session.total_seat_count,
			"warning_count": session.warning_count,
			"notice_count": session.notice_count,
			"event_count": session.event_count,
		},
	}


@router.get("/session/events")
def session_events(
	x_session_id = Header(default = None, alias = "X-Session-Id"),
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	session_id = parse_header_int(x_session_id, "X-Session-Id", required = True)
	_ensure_session_access(db, context, session_id)
	rows = db.query(MonitorBehaviorEvent).filter(MonitorBehaviorEvent.session_id == session_id).order_by(MonitorBehaviorEvent.event_time.desc()).all()
	return {
		"ok": True,
		"events": [
			{
				"id": row.id,
				"event_id": row.event_uid,
				"time": row.event_time,
				"seat": row.seat_code,
				"level": row.level,
				"status": row.status,
				"label": row.label,
				"reason": row.reason,
				"source": row.source,
				"analysis_source": row.analysis_source,
				"url": row.image_url,
				"box": [float(row.box_x1 or 0), float(row.box_y1 or 0), float(row.box_x2 or 0), float(row.box_y2 or 0)],
			}
			for row in rows
		],
	}


@router.get("/event/detail")
def event_detail(
	x_event_id = Header(default = None, alias = "X-Event-Id"),
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	event_id = parse_header_int(x_event_id, "X-Event-Id", required = True)
	event = db.query(MonitorBehaviorEvent).filter(MonitorBehaviorEvent.id == event_id).first()
	if not event:
		raise HTTPException(status_code = 404, detail = "事件不存在")
	session = _ensure_session_access(db, context, event.session_id)
	frames = db.query(MonitorEventFrame).filter(MonitorEventFrame.event_id == event.id).order_by(MonitorEventFrame.frame_index.asc()).all()
	return {
		"ok": True,
		"event": {
			"id": event.id,
			"event_id": event.event_uid,
			"session_id": event.session_id,
			"class_name": session.class_name,
			"seat": event.seat_code,
			"level": event.level,
			"status": event.status,
			"label": event.label,
			"reason": event.reason,
			"source": event.source,
			"analysis_source": event.analysis_source,
			"alert_start_time": event.event_time,
			"list_image_url": event.image_url,
			"box": [float(event.box_x1 or 0), float(event.box_y1 or 0), float(event.box_x2 or 0), float(event.box_y2 or 0)],
			"frames": [
				{
					"frame_index": frame.frame_index,
					"time": frame.frame_time,
					"focus_image_url": frame.focus_image_url,
					"seat": {
						"seat_name": frame.seat_code,
						"status": frame.status,
						"status_text": frame.status_text,
						"ratio": float(frame.ratio) if frame.ratio is not None else None,
						"box_conf": float(frame.box_conf) if frame.box_conf is not None else None,
					},
				}
				for frame in frames
			],
		},
	}


@router.get("/session/review")
def get_review(
	x_session_id = Header(default = None, alias = "X-Session-Id"),
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	session_id = parse_header_int(x_session_id, "X-Session-Id", required = True)
	session = _ensure_session_access(db, context, session_id)
	teacher = context.get("teacher")
	if not teacher:
		return { "ok": True, "review": None }
	row = db.query(MonitorTeachingReview).filter(MonitorTeachingReview.session_id == session.id, MonitorTeachingReview.teacher_id == teacher.id).first()
	return {
		"ok": True,
		"review": None if not row else {
			"id": row.id,
			"review_status": row.review_status,
			"teaching_effect_score": float(row.teaching_effect_score) if row.teaching_effect_score is not None else None,
			"focus_summary": row.focus_summary,
			"problem_summary": row.problem_summary,
			"improvement_plan": row.improvement_plan,
			"reviewed_at": row.reviewed_at,
		},
	}


@router.post("/session/review")
async def save_review(
	request: Request,
	x_session_id = Header(default = None, alias = "X-Session-Id"),
	x_teacher_id = Header(default = None, alias = "X-Teacher-Id"),
	context = Depends(get_current_context),
	db: Session = Depends(get_db),
):
	session_id = parse_header_int(x_session_id, "X-Session-Id", required = True)
	teacher_id = parse_header_int(x_teacher_id, "X-Teacher-Id")
	session = _ensure_session_access(db, context, session_id)
	teacher = _ensure_review_teacher(db, context, session, teacher_id)
	body = await request.json()
	score = (body or {}).get("teaching_effect_score")
	row = (
		db.query(MonitorTeachingReview)
		.filter(MonitorTeachingReview.session_id == session.id, MonitorTeachingReview.teacher_id == teacher.id)
		.first()
	)
	if not row:
		row = MonitorTeachingReview(session_id = session.id, teacher_id = teacher.id)
		db.add(row)
	row.review_status = "REVIEWED"
	row.teaching_effect_score = score
	row.focus_summary = (body or {}).get("focus_summary", "")
	row.problem_summary = (body or {}).get("problem_summary", "")
	row.improvement_plan = (body or {}).get("improvement_plan", "")
	row.reviewed_at = datetime.utcnow()
	db.commit()
	return {
		"ok": True,
		"review": {
			"id": row.id,
			"session_id": row.session_id,
			"teacher_id": row.teacher_id,
			"review_status": row.review_status,
			"teaching_effect_score": float(row.teaching_effect_score) if row.teaching_effect_score is not None else None,
			"focus_summary": row.focus_summary,
			"problem_summary": row.problem_summary,
			"improvement_plan": row.improvement_plan,
			"reviewed_at": row.reviewed_at,
		},
	}
