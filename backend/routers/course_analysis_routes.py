"""教师教学课程分析串联、改进措施、汇总与报告接口。"""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_context, is_admin
from domain.models import (
	CourseAnalysisAggregate,
	CourseAnalysisEntry,
	CourseBehaviorStat,
	EduAcademicTerm,
	EduAcademicYear,
	EduClass,
	EduLessonSchedule,
	EduSubject,
	EduTeacher,
	LessonAnalysisSummary,
	LessonBehaviorStat,
	MonitorSession,
	TeachingAnalysisReport,
	TeachingCourse,
	TeachingImprovementAction,
)
from services.teaching_analysis_service import refresh_course_aggregate


router = APIRouter(prefix = "/api/teacher", tags = ["course-analysis"])


def _text(body, key):
	return str((body or {}).get(key, "") or "").strip()


def _bool(body, key, default = False):
	value = (body or {}).get(key)
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	if isinstance(value, int) and value in { 0, 1 }:
		return bool(value)
	if isinstance(value, str) and value.strip().lower() in { "true", "1" }:
		return True
	if isinstance(value, str) and value.strip().lower() in { "false", "0" }:
		return False
	raise HTTPException(status_code = 400, detail = f"{key} 必须是布尔值")


def _current_teacher(context):
	teacher = context.get("teacher")
	if not teacher:
		raise HTTPException(status_code = 403, detail = "当前账号未绑定教师档案")
	return teacher


def _course(db, course_id):
	row = db.query(TeachingCourse).filter(TeachingCourse.id == course_id).first()
	if not row:
		raise HTTPException(status_code = 404, detail = "教学课程不存在")
	return row


def _ensure_course_access(db, context, course_id, writable = False):
	course = _course(db, course_id)
	if is_admin(context):
		return course
	teacher = _current_teacher(context)
	if course.teacher_id != teacher.id:
		action = "修改" if writable else "查看"
		raise HTTPException(status_code = 403, detail = f"无权{action}该教学课程")
	return course


def _course_maps(db):
	return (
		{ row.id: row for row in db.query(EduAcademicYear).all() },
		{ row.id: row for row in db.query(EduAcademicTerm).all() },
		{ row.id: row for row in db.query(EduClass).all() },
		{ row.id: row for row in db.query(EduSubject).all() },
		{ row.id: row for row in db.query(EduTeacher).all() },
	)


def _serialize_course(row, years, terms, classes, subjects, teachers, entry_count = 0, action_count = 0, pending_count = 0):
	term = terms.get(row.term_id)
	year = years.get(term.academic_year_id) if term else None
	cls = classes.get(row.class_id)
	subject = subjects.get(row.subject_id)
	teacher = teachers.get(row.teacher_id)
	return {
		"id": row.id,
		"course_no": row.course_no,
		"course_name": row.course_name,
		"term_id": row.term_id,
		"term_name": term.term_name if term else "",
		"academic_year_id": term.academic_year_id if term else None,
		"academic_year_name": year.year_name if year else "",
		"class_id": row.class_id,
		"class_name": cls.class_name if cls else "",
		"subject_id": row.subject_id,
		"subject_name": subject.subject_name if subject else "",
		"teacher_id": row.teacher_id,
		"teacher_name": teacher.teacher_name if teacher else "",
		"planned_lesson_count": row.planned_lesson_count,
		"start_date": row.start_date,
		"end_date": row.end_date,
		"status": row.status,
		"entry_count": entry_count,
		"open_action_count": action_count,
		"pending_analysis_count": pending_count,
	}


def _is_schedule_current(course, term, schedule, now):
	"""判断固定课表是否正处于当前本地时段，供“我的班级”实时展示当前课程。"""
	if not term or term.status != "ENABLED" or course.status != "ACTIVE" or schedule.weekday != now.isoweekday():
		return False
	if now.date() < term.start_date or now.date() > term.end_date:
		return False
	if course.start_date and now.date() < course.start_date:
		return False
	if course.end_date and now.date() > course.end_date:
		return False
	try:
		start_at = datetime.strptime(schedule.start_time, "%H:%M").time()
		end_at = datetime.strptime(schedule.end_time, "%H:%M").time()
	except ValueError:
		return False
	current_time = now.time().replace(microsecond = 0)
	return start_at <= current_time < end_at


def _serialize_current_course(course, schedule):
	return {
		"id": course.id,
		"course_name": course.course_name,
		"lesson_title": schedule.lesson_title or "",
		"start_time": schedule.start_time,
		"end_time": schedule.end_time,
	}


def _serialize_entry(db, row):
	session = db.query(MonitorSession).filter(MonitorSession.id == row.session_id).first()
	summary = db.query(LessonAnalysisSummary).filter(LessonAnalysisSummary.id == row.summary_id).first()
	base = db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.id == row.comparison_base_entry_id).first() if row.comparison_base_entry_id else None
	stats = db.query(LessonBehaviorStat).filter(LessonBehaviorStat.summary_id == row.summary_id).order_by(LessonBehaviorStat.event_count.desc()).all()
	return {
		"id": row.id,
		"session_id": row.session_id,
		"report_id": row.report_id,
		"lesson_index": row.lesson_index,
		"lesson_date": row.lesson_date,
		"lesson_title": row.lesson_title or (session.lesson_title if session else "") or "未命名课次",
		"event_count": summary.event_count if summary else 0,
		"confirmed_event_count": summary.confirmed_event_count if summary else 0,
		"valid_analysis_seconds": summary.valid_analysis_seconds if summary else 0,
		"data_quality_level": summary.data_quality_level if summary else "UNAVAILABLE",
		"quality_remark": summary.quality_remark if summary else "",
		"behavior_stats": [
			{
				"behavior_code": stat.behavior_code,
				"event_count": stat.event_count,
				"duration_ratio": float(stat.duration_ratio),
				"vlm_confirmed_count": stat.vlm_confirmed_count,
			}
			for stat in stats
		],
		"comparison_base_entry_id": row.comparison_base_entry_id,
		"comparison_base_lesson_index": base.lesson_index if base else None,
		"system_change_summary": row.system_change_summary or "",
		"teacher_change_note": row.teacher_change_note or "",
		"is_baseline": bool(row.is_baseline),
		"is_milestone": bool(row.is_milestone),
	}


def _serialize_action(db, row):
	source = db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.id == row.source_entry_id).first()
	verified = db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.id == row.verified_by_entry_id).first() if row.verified_by_entry_id else None
	return {
		"id": row.id,
		"source_entry_id": row.source_entry_id,
		"source_lesson_index": source.lesson_index if source else None,
		"issue_type": row.issue_type or "",
		"issue_description": row.issue_description,
		"improvement_plan": row.improvement_plan,
		"planned_for_entry_id": row.planned_for_entry_id,
		"action_status": row.action_status,
		"implemented_at": row.implemented_at,
		"verified_by_entry_id": row.verified_by_entry_id,
		"verified_lesson_index": verified.lesson_index if verified else None,
		"verification_note": row.verification_note or "",
		"verified_at": row.verified_at,
	}


def _serialize_report(row):
	return {
		"id": row.id,
		"report_no": row.report_no,
		"report_title": row.report_title,
		"report_scope": row.report_scope,
		"session_id": row.session_id,
		"aggregate_id": row.aggregate_id,
		"teaching_course_id": row.teaching_course_id,
		"report_version": row.report_version,
		"report_status": row.report_status,
		"generated_mode": row.generated_mode,
		"overview_text": row.overview_text or "",
		"finding_text": row.finding_text or "",
		"suggestion_text": row.suggestion_text or "",
		"teacher_conclusion": row.teacher_conclusion or "",
		"data_snapshot_json": row.data_snapshot_json or {},
		"published_at": row.published_at,
	}


@router.get("/teaching-courses")
def teacher_teaching_courses(context = Depends(get_current_context), db: Session = Depends(get_db)):
	query = db.query(TeachingCourse)
	if not is_admin(context):
		query = query.filter(TeachingCourse.teacher_id == _current_teacher(context).id)
	rows = query.order_by(TeachingCourse.created_at.desc()).all()
	years, terms, classes, subjects, teachers = _course_maps(db)
	items = []
	for row in rows:
		entry_count = db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.teaching_course_id == row.id).count()
		action_count = db.query(TeachingImprovementAction).filter(
			TeachingImprovementAction.teaching_course_id == row.id,
			TeachingImprovementAction.action_status.in_(["PLANNED", "IMPLEMENTED"]),
		).count()
		pending_count = db.query(MonitorSession).filter(
			MonitorSession.teaching_course_id == row.id,
			MonitorSession.analysis_status.in_(["PENDING", "RUNNING"]),
		).count()
		items.append(_serialize_course(row, years, terms, classes, subjects, teachers, entry_count, action_count, pending_count))
	return { "ok": True, "items": items }


@router.get("/my-classes")
def teacher_my_classes(context = Depends(get_current_context), db: Session = Depends(get_db)):
	"""按班级汇总教师的教学课程，并在每次请求时匹配当前固定课表。"""
	query = db.query(TeachingCourse)
	if not is_admin(context):
		query = query.filter(TeachingCourse.teacher_id == _current_teacher(context).id)
	rows = query.order_by(TeachingCourse.created_at.desc()).all()
	years, terms, classes, subjects, teachers = _course_maps(db)
	now = datetime.now()
	course_ids = [row.id for row in rows]
	schedules_by_course = {}
	if course_ids:
		for schedule in db.query(EduLessonSchedule).filter(
			EduLessonSchedule.enabled == 1,
			EduLessonSchedule.teaching_course_id.in_(course_ids),
		).all():
			schedules_by_course.setdefault(schedule.teaching_course_id, []).append(schedule)

	class_items = {}
	for row in rows:
		term = terms.get(row.term_id)
		cls = classes.get(row.class_id)
		item = class_items.setdefault(row.class_id, {
			"class_id": row.class_id,
			"class_name": cls.class_name if cls else "",
			"course_count": 0,
			"planned_lesson_count": 0,
			"entry_count": 0,
			"open_action_count": 0,
			"pending_analysis_count": 0,
			"current_course": None,
			"_default_course": row,
			"_display_term": term,
			"_course_ids": [],
		})
		item["course_count"] += 1
		item["planned_lesson_count"] += row.planned_lesson_count or 0
		item["_course_ids"].append(row.id)
		if item["current_course"] is None:
			for schedule in schedules_by_course.get(row.id, []):
				if _is_schedule_current(row, term, schedule, now):
					item["current_course"] = _serialize_current_course(row, schedule)
					item["_default_course"] = row
					item["_display_term"] = term
					break

	items = []
	for item in class_items.values():
		course_id_list = item.pop("_course_ids")
		item["entry_count"] = db.query(CourseAnalysisEntry).filter(
			CourseAnalysisEntry.teaching_course_id.in_(course_id_list),
		).count()
		item["open_action_count"] = db.query(TeachingImprovementAction).filter(
			TeachingImprovementAction.teaching_course_id.in_(course_id_list),
			TeachingImprovementAction.action_status.in_(["PLANNED", "IMPLEMENTED"]),
		).count()
		item["pending_analysis_count"] = db.query(MonitorSession).filter(
			MonitorSession.teaching_course_id.in_(course_id_list),
			MonitorSession.analysis_status.in_(["PENDING", "RUNNING"]),
		).count()
		default_course = item.pop("_default_course")
		display_term = item.pop("_display_term")
		display_year = years.get(display_term.academic_year_id) if display_term else None
		item["academic_year_name"] = display_year.year_name if display_year else ""
		item["term_name"] = display_term.term_name if display_term else ""
		item["teacher_name"] = teachers.get(default_course.teacher_id).teacher_name if teachers.get(default_course.teacher_id) else ""
		# 没有当前课次时仍可进入该班唯一/默认课程的历史报告；当前课次存在时优先进入它。
		item["report_course_id"] = item["current_course"]["id"] if item["current_course"] else default_course.id
		items.append(item)

	items.sort(key = lambda item: item["class_name"])
	return { "ok": True, "queried_at": now.isoformat(timespec = "seconds"), "items": items }


@router.get("/teaching-courses/{course_id}/entries")
def teacher_course_entries(course_id: int, context = Depends(get_current_context), db: Session = Depends(get_db)):
	_ensure_course_access(db, context, course_id)
	rows = (
		db.query(CourseAnalysisEntry)
		.filter(CourseAnalysisEntry.teaching_course_id == course_id)
		.order_by(CourseAnalysisEntry.lesson_date.asc(), CourseAnalysisEntry.lesson_index.asc())
		.all()
	)
	return { "ok": True, "items": [_serialize_entry(db, row) for row in rows] }


@router.put("/course-analysis-entries/{entry_id}")
async def update_course_analysis_entry(entry_id: int, request: Request, context = Depends(get_current_context), db: Session = Depends(get_db)):
	row = db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.id == entry_id).first()
	if not row:
		raise HTTPException(status_code = 404, detail = "课程分析条目不存在")
	_ensure_course_access(db, context, row.teaching_course_id, writable = True)
	body = await request.json()
	if "teacher_change_note" in (body or {}):
		row.teacher_change_note = _text(body, "teacher_change_note") or None
	if "is_milestone" in (body or {}):
		row.is_milestone = 1 if _bool(body, "is_milestone") else 0
	# 基线用于后续课次的纵向对比。取消勾选时也要持久化，避免前端状态与数据库不一致。
	if "is_baseline" in (body or {}):
		if _bool(body, "is_baseline"):
			db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.teaching_course_id == row.teaching_course_id).update({ "is_baseline": 0 })
			row.is_baseline = 1
			# 之后新产生的条目可继续以该课次为比较基准，已完成条目不静默改写。
		else:
			row.is_baseline = 0
	db.commit()
	return { "ok": True, "item": _serialize_entry(db, row) }


@router.get("/teaching-courses/{course_id}/improvement-actions")
def improvement_actions(course_id: int, context = Depends(get_current_context), db: Session = Depends(get_db)):
	_ensure_course_access(db, context, course_id)
	rows = (
		db.query(TeachingImprovementAction)
		.filter(TeachingImprovementAction.teaching_course_id == course_id)
		.order_by(TeachingImprovementAction.created_at.desc())
		.all()
	)
	return { "ok": True, "items": [_serialize_action(db, row) for row in rows] }


@router.post("/teaching-courses/{course_id}/improvement-actions")
async def create_improvement_action(course_id: int, request: Request, context = Depends(get_current_context), db: Session = Depends(get_db)):
	_ensure_course_access(db, context, course_id, writable = True)
	teacher = _current_teacher(context)
	body = await request.json()
	try:
		source_entry_id = int((body or {}).get("source_entry_id"))
	except (TypeError, ValueError) as exc:
		raise HTTPException(status_code = 400, detail = "请选择问题来源课次") from exc
	source = db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.id == source_entry_id, CourseAnalysisEntry.teaching_course_id == course_id).first()
	if not source:
		raise HTTPException(status_code = 400, detail = "问题来源课次不属于当前课程")
	issue_description = _text(body, "issue_description")
	improvement_plan = _text(body, "improvement_plan")
	if not issue_description or not improvement_plan:
		raise HTTPException(status_code = 400, detail = "请填写问题说明和改进措施")
	row = TeachingImprovementAction(
		teaching_course_id = course_id,
		source_entry_id = source_entry_id,
		issue_type = _text(body, "issue_type") or None,
		issue_description = issue_description,
		improvement_plan = improvement_plan,
		created_by = teacher.id,
	)
	db.add(row)
	db.commit()
	return { "ok": True, "item": _serialize_action(db, row) }


@router.put("/improvement-actions/{action_id}")
async def update_improvement_action(action_id: int, request: Request, context = Depends(get_current_context), db: Session = Depends(get_db)):
	row = db.query(TeachingImprovementAction).filter(TeachingImprovementAction.id == action_id).first()
	if not row:
		raise HTTPException(status_code = 404, detail = "教学改进措施不存在")
	_ensure_course_access(db, context, row.teaching_course_id, writable = True)
	body = await request.json()
	status = _text(body, "action_status").upper() or row.action_status
	if status not in { "PLANNED", "IMPLEMENTED", "VERIFIED", "CLOSED" }:
		raise HTTPException(status_code = 400, detail = "改进措施状态无效")
	if "issue_description" in (body or {}):
		row.issue_description = _text(body, "issue_description") or row.issue_description
	if "improvement_plan" in (body or {}):
		row.improvement_plan = _text(body, "improvement_plan") or row.improvement_plan
	row.action_status = status
	if status == "IMPLEMENTED" and not row.implemented_at:
		row.implemented_at = datetime.utcnow()
	if status in { "VERIFIED", "CLOSED" }:
		verify_id = (body or {}).get("verified_by_entry_id")
		if verify_id not in (None, ""):
			try:
				verify_id = int(verify_id)
			except (TypeError, ValueError) as exc:
				raise HTTPException(status_code = 400, detail = "验证课次必须是整数") from exc
			verify_entry = db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.id == verify_id, CourseAnalysisEntry.teaching_course_id == row.teaching_course_id).first()
			if not verify_entry:
				raise HTTPException(status_code = 400, detail = "验证课次不属于当前课程")
			row.verified_by_entry_id = verify_entry.id
		row.verification_note = _text(body, "verification_note") or None
		row.verified_at = datetime.utcnow()
	db.commit()
	return { "ok": True, "item": _serialize_action(db, row) }


@router.post("/teaching-courses/{course_id}/aggregates/refresh")
async def refresh_aggregate(course_id: int, request: Request, context = Depends(get_current_context), db: Session = Depends(get_db)):
	_ensure_course_access(db, context, course_id, writable = True)
	body = await request.json()
	scope_type = _text(body, "scope_type").upper() or "TERM"
	try:
		aggregate = refresh_course_aggregate(db, course_id, scope_type)
	except ValueError as exc:
		raise HTTPException(status_code = 400, detail = str(exc)) from exc
	db.commit()
	return { "ok": True, "aggregate_id": aggregate.id }


@router.get("/teaching-courses/{course_id}/aggregates")
def course_aggregates(course_id: int, context = Depends(get_current_context), db: Session = Depends(get_db)):
	_ensure_course_access(db, context, course_id)
	rows = db.query(CourseAnalysisAggregate).filter(CourseAnalysisAggregate.teaching_course_id == course_id).order_by(CourseAnalysisAggregate.calculated_at.desc()).all()
	items = []
	for row in rows:
		stats = db.query(CourseBehaviorStat).filter(CourseBehaviorStat.aggregate_id == row.id).order_by(CourseBehaviorStat.event_count.desc()).all()
		items.append({
			"id": row.id,
			"scope_type": row.scope_type,
			"period_start_date": row.period_start_date,
			"period_end_date": row.period_end_date,
			"source_session_count": row.source_session_count,
			"completed_session_count": row.completed_session_count,
			"valid_analysis_seconds": row.valid_analysis_seconds,
			"data_quality_level": row.data_quality_level,
			"aggregate_status": row.aggregate_status,
			"calculated_at": row.calculated_at,
			"behavior_stats": [
				{
					"behavior_code": stat.behavior_code,
					"event_count": stat.event_count,
					"average_per_session": float(stat.average_per_session),
					"session_coverage_count": stat.session_coverage_count,
				}
				for stat in stats
			],
		})
	return { "ok": True, "items": items }


@router.get("/teaching-courses/{course_id}/reports")
def course_reports(course_id: int, context = Depends(get_current_context), db: Session = Depends(get_db)):
	_ensure_course_access(db, context, course_id)
	rows = db.query(TeachingAnalysisReport).filter(TeachingAnalysisReport.teaching_course_id == course_id).order_by(TeachingAnalysisReport.created_at.desc()).all()
	return { "ok": True, "items": [_serialize_report(row) for row in rows] }


@router.post("/teaching-courses/{course_id}/reports")
async def create_course_report(course_id: int, request: Request, context = Depends(get_current_context), db: Session = Depends(get_db)):
	course = _ensure_course_access(db, context, course_id, writable = True)
	body = await request.json()
	aggregate_id = (body or {}).get("aggregate_id")
	aggregate = db.query(CourseAnalysisAggregate).filter(CourseAnalysisAggregate.id == aggregate_id, CourseAnalysisAggregate.teaching_course_id == course_id).first() if aggregate_id else None
	if not aggregate:
		raise HTTPException(status_code = 400, detail = "请选择当前课程的有效汇总")
	existing = (
		db.query(TeachingAnalysisReport)
		.filter(
			TeachingAnalysisReport.teaching_course_id == course_id,
			TeachingAnalysisReport.aggregate_id == aggregate.id,
		)
		.order_by(TeachingAnalysisReport.report_version.desc())
		.first()
	)
	if existing and existing.report_status != "PUBLISHED":
		raise HTTPException(status_code = 409, detail = "该汇总已有未发布报告，请继续编辑现有草稿")
	latest = (
		db.query(TeachingAnalysisReport.report_version)
		.filter(TeachingAnalysisReport.teaching_course_id == course_id)
		.order_by(TeachingAnalysisReport.report_version.desc())
		.first()
	)
	report_version = (latest[0] if latest else 0) + 1
	stats = db.query(CourseBehaviorStat).filter(CourseBehaviorStat.aggregate_id == aggregate.id).all()
	finding = "、".join(f"{item.behavior_code} {item.event_count} 次" for item in stats) or "当前汇总没有可用行为统计。"
	report = TeachingAnalysisReport(
		report_no = f"CR{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid4().hex[:6]}",
		report_title = _text(body, "report_title") or f"{course.course_name}课程阶段分析报告",
		report_scope = "COURSE",
		aggregate_id = aggregate.id,
		teaching_course_id = course_id,
		report_version = report_version,
		overview_text = f"本报告覆盖 {aggregate.completed_session_count} 节已完成分析的课次，有效分析时长 {aggregate.valid_analysis_seconds} 秒。",
		finding_text = f"课程阶段统计：{finding}",
		suggestion_text = "请结合课程内容和已记录的教学改进措施，由教师形成阶段性结论。",
		data_snapshot_json = {
			"aggregate_id": aggregate.id,
			"source_session_count": aggregate.source_session_count,
			"completed_session_count": aggregate.completed_session_count,
			"data_quality_level": aggregate.data_quality_level,
		},
	)
	db.add(report)
	db.commit()
	return { "ok": True, "item": _serialize_report(report) }


@router.put("/teaching-analysis-reports/{report_id}")
async def update_course_report(report_id: int, request: Request, context = Depends(get_current_context), db: Session = Depends(get_db)):
	report = db.query(TeachingAnalysisReport).filter(TeachingAnalysisReport.id == report_id).first()
	if not report or not report.teaching_course_id:
		raise HTTPException(status_code = 404, detail = "课程报告不存在")
	_ensure_course_access(db, context, report.teaching_course_id, writable = True)
	if report.report_status == "PUBLISHED":
		raise HTTPException(status_code = 409, detail = "已发布报告不可直接修改，请创建新版本")
	body = await request.json()
	report.teacher_conclusion = _text(body, "teacher_conclusion") or None
	report.finding_text = _text(body, "finding_text") or report.finding_text
	report.suggestion_text = _text(body, "suggestion_text") or report.suggestion_text
	report.generated_mode = "TEACHER_EDITED"
	if _bool(body, "publish"):
		report.report_status = "PUBLISHED"
		report.published_by = context["user"].id
		report.published_at = datetime.utcnow()
	db.commit()
	return { "ok": True, "item": _serialize_report(report) }
