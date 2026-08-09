"""学期、教学课程、课表与固定摄像设备管理接口。"""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_admin
from domain.models import (
	CameraClassBinding,
	CameraDevice,
	EduAcademicTerm,
	EduAcademicYear,
	EduClass,
	EduLessonSchedule,
	EduSubject,
	EduTeacher,
	TeachingCourse,
)


router = APIRouter(prefix = "/api/admin", tags = ["teaching-admin"])
ACADEMIC_STATUSES = { "ENABLED", "DISABLED" }
COURSE_STATUSES = { "DRAFT", "ACTIVE", "ARCHIVED" }


def _text(body, key):
	return str((body or {}).get(key, "") or "").strip()


def _required_text(body, key, title):
	value = _text(body, key)
	if not value:
		raise HTTPException(status_code = 400, detail = f"{title}不能为空")
	return value


def _int(body, key, title, required = True):
	value = (body or {}).get(key)
	if value in (None, ""):
		if required:
			raise HTTPException(status_code = 400, detail = f"{title}不能为空")
		return None
	try:
		return int(value)
	except (TypeError, ValueError) as exc:
		raise HTTPException(status_code = 400, detail = f"{title}必须是整数") from exc


def _bool(body, key, default = True):
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


def _date(body, key, title, required = True):
	value = _text(body, key)
	if not value:
		if required:
			raise HTTPException(status_code = 400, detail = f"{title}不能为空")
		return None
	try:
		return datetime.strptime(value, "%Y-%m-%d").date()
	except ValueError as exc:
		raise HTTPException(status_code = 400, detail = f"{title}必须为 YYYY-MM-DD") from exc


def _time_text(body, key, title):
	value = _required_text(body, key, title)
	try:
		parsed = datetime.strptime(value, "%H:%M")
	except ValueError as exc:
		raise HTTPException(status_code = 400, detail = f"{title}必须为 HH:MM") from exc
	return parsed.strftime("%H:%M")


def _get(db, model, row_id, title):
	row = db.query(model).filter(model.id == row_id).first()
	if not row:
		raise HTTPException(status_code = 404, detail = f"{title}不存在")
	return row


def _serialize_year(row):
	return {
		"id": row.id,
		"year_name": row.year_name,
		"start_date": row.start_date,
		"end_date": row.end_date,
		"status": row.status,
	}


def _serialize_term(row, years_by_id):
	return {
		"id": row.id,
		"academic_year_id": row.academic_year_id,
		"academic_year_name": years_by_id.get(row.academic_year_id).year_name if years_by_id.get(row.academic_year_id) else "",
		"term_name": row.term_name,
		"start_date": row.start_date,
		"end_date": row.end_date,
		"status": row.status,
	}


def _serialize_course(row, terms_by_id, classes_by_id, subjects_by_id, teachers_by_id):
	term = terms_by_id.get(row.term_id)
	cls = classes_by_id.get(row.class_id)
	subject = subjects_by_id.get(row.subject_id)
	teacher = teachers_by_id.get(row.teacher_id)
	return {
		"id": row.id,
		"course_no": row.course_no,
		"term_id": row.term_id,
		"term_name": term.term_name if term else "",
		"class_id": row.class_id,
		"class_name": cls.class_name if cls else "",
		"subject_id": row.subject_id,
		"subject_name": subject.subject_name if subject else "",
		"teacher_id": row.teacher_id,
		"teacher_name": teacher.teacher_name if teacher else "",
		"course_name": row.course_name,
		"planned_lesson_count": row.planned_lesson_count,
		"start_date": row.start_date,
		"end_date": row.end_date,
		"status": row.status,
	}


def _course_options(db):
	return (
		{ row.id: row for row in db.query(EduAcademicTerm).all() },
		{ row.id: row for row in db.query(EduClass).all() },
		{ row.id: row for row in db.query(EduSubject).all() },
		{ row.id: row for row in db.query(EduTeacher).all() },
	)


def _apply_year(row, body):
	start_date = _date(body, "start_date", "开始日期")
	end_date = _date(body, "end_date", "结束日期")
	if end_date <= start_date:
		raise HTTPException(status_code = 400, detail = "结束日期必须晚于开始日期")
	row.year_name = _required_text(body, "year_name", "学年名称")
	row.start_date = start_date
	row.end_date = end_date
	status = _text(body, "status").upper() or "ENABLED"
	if status not in ACADEMIC_STATUSES:
		raise HTTPException(status_code = 400, detail = "学年状态无效")
	row.status = status


def _apply_term(db, row, body):
	academic_year_id = _int(body, "academic_year_id", "所属学年")
	year = _get(db, EduAcademicYear, academic_year_id, "学年")
	start_date = _date(body, "start_date", "开始日期")
	end_date = _date(body, "end_date", "结束日期")
	if end_date <= start_date:
		raise HTTPException(status_code = 400, detail = "结束日期必须晚于开始日期")
	if start_date < year.start_date or end_date > year.end_date:
		raise HTTPException(status_code = 400, detail = "学期日期必须位于所属学年内")
	row.academic_year_id = academic_year_id
	row.term_name = _required_text(body, "term_name", "学期名称")
	row.start_date = start_date
	row.end_date = end_date
	status = _text(body, "status").upper() or "ENABLED"
	if status not in ACADEMIC_STATUSES:
		raise HTTPException(status_code = 400, detail = "学期状态无效")
	row.status = status


def _apply_course(db, row, body):
	term_id = _int(body, "term_id", "所属学期")
	class_id = _int(body, "class_id", "授课班级")
	subject_id = _int(body, "subject_id", "授课科目")
	teacher_id = _int(body, "teacher_id", "任课教师", required = False)
	term = _get(db, EduAcademicTerm, term_id, "学期")
	_get(db, EduClass, class_id, "班级")
	_get(db, EduSubject, subject_id, "科目")
	if teacher_id is not None:
		_get(db, EduTeacher, teacher_id, "教师")
	start_date = _date(body, "start_date", "课程开始日期", required = False)
	end_date = _date(body, "end_date", "课程结束日期", required = False)
	if start_date and end_date and end_date < start_date:
		raise HTTPException(status_code = 400, detail = "课程结束日期不能早于开始日期")
	if start_date and start_date < term.start_date:
		raise HTTPException(status_code = 400, detail = "课程开始日期不能早于学期开始日期")
	if end_date and end_date > term.end_date:
		raise HTTPException(status_code = 400, detail = "课程结束日期不能晚于学期结束日期")
	row.course_no = _text(body, "course_no") or row.course_no or f"TC{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid4().hex[:4]}"
	row.term_id = term_id
	row.class_id = class_id
	row.subject_id = subject_id
	row.teacher_id = teacher_id
	row.course_name = _required_text(body, "course_name", "课程名称")
	planned_lesson_count = (body or {}).get("planned_lesson_count")
	if planned_lesson_count in (None, ""):
		row.planned_lesson_count = None
	else:
		try:
			row.planned_lesson_count = int(planned_lesson_count)
		except (TypeError, ValueError) as exc:
			raise HTTPException(status_code = 400, detail = "计划课次必须是整数") from exc
		if row.planned_lesson_count <= 0:
			raise HTTPException(status_code = 400, detail = "计划课次必须大于 0")
	row.start_date = start_date
	row.end_date = end_date
	status = _text(body, "status").upper() or "DRAFT"
	if status not in COURSE_STATUSES:
		raise HTTPException(status_code = 400, detail = "教学课程状态无效")
	row.status = status


def _check_schedule_overlap(db, row, course, weekday, start_time, end_time, enabled):
	"""同一班级、同一学期内的有效课表不得占用重叠时段。"""
	if not enabled:
		return
	rows = (
		db.query(EduLessonSchedule, TeachingCourse, EduAcademicTerm)
		.join(TeachingCourse, TeachingCourse.id == EduLessonSchedule.teaching_course_id)
		.join(EduAcademicTerm, EduAcademicTerm.id == TeachingCourse.term_id)
		.filter(
			EduLessonSchedule.id != (row.id or 0),
			EduLessonSchedule.enabled == 1,
			TeachingCourse.class_id == course.class_id,
			TeachingCourse.term_id == course.term_id,
			EduLessonSchedule.weekday == weekday,
			EduLessonSchedule.start_time < end_time,
			EduLessonSchedule.end_time > start_time,
		)
		.all()
	)
	new_start = course.start_date or course.term.start_date
	new_end = course.end_date or course.term.end_date
	for other_schedule, other_course, term in rows:
		other_start = other_course.start_date or term.start_date
		other_end = other_course.end_date or term.end_date
		if max(new_start, other_start) <= min(new_end, other_end):
			raise HTTPException(status_code = 409, detail = "同一班级存在时间重叠的有效课表")


def _check_existing_course_schedules(db, course):
	"""课程班级、学期或日期变更后，重新校验其已经保存的全部有效课表。"""
	rows = db.query(EduLessonSchedule).filter(
		EduLessonSchedule.teaching_course_id == course.id,
		EduLessonSchedule.enabled == 1,
	).all()
	for schedule in rows:
		_check_schedule_overlap(db, schedule, course, schedule.weekday, schedule.start_time, schedule.end_time, True)


def _apply_schedule(db, row, body):
	course_id = _int(body, "teaching_course_id", "教学课程")
	course = _get(db, TeachingCourse, course_id, "教学课程")
	weekday = _int(body, "weekday", "星期")
	if weekday not in range(1, 8):
		raise HTTPException(status_code = 400, detail = "星期必须为 1 至 7")
	start_time = _time_text(body, "start_time", "开始时间")
	end_time = _time_text(body, "end_time", "结束时间")
	if end_time <= start_time:
		raise HTTPException(status_code = 400, detail = "结束时间必须晚于开始时间")
	enabled = _bool(body, "enabled", True)
	_check_schedule_overlap(db, row, course, weekday, start_time, end_time, enabled)
	row.teaching_course_id = course_id
	row.weekday = weekday
	row.start_time = start_time
	row.end_time = end_time
	row.lesson_title = _text(body, "lesson_title") or None
	row.enabled = 1 if enabled else 0


def _apply_camera(db, row, body):
	device_code = _required_text(body, "device_code", "设备编号")
	exists = db.query(CameraDevice).filter(CameraDevice.device_code == device_code, CameraDevice.id != (row.id or 0)).first()
	if exists:
		raise HTTPException(status_code = 400, detail = "设备编号已存在")
	row.device_code = device_code
	row.device_name = _required_text(body, "device_name", "设备名称")
	row.location = _text(body, "location") or None
	row.source_path = _text(body, "source_path") or None
	row.enabled = 1 if _bool(body, "enabled", True) else 0
	row.remark = _text(body, "remark") or None


def _check_binding_overlap(db, row, camera_id, class_id, start_date, end_date):
	"""一个有效期内，摄像头与班级都只能出现一次有效绑定，避免解析时随机选取来源。"""
	rows = db.query(CameraClassBinding).filter(
		CameraClassBinding.id != (row.id or 0),
		CameraClassBinding.enabled == 1,
		or_(CameraClassBinding.camera_id == camera_id, CameraClassBinding.class_id == class_id),
	).all()
	for other in rows:
		other_end = other.effective_end_date
		if (end_date is None or other.effective_start_date < end_date) and (other_end is None or start_date < other_end):
			if other.camera_id == camera_id:
				raise HTTPException(status_code = 400, detail = "同一摄像设备存在重叠的有效班级绑定")
			raise HTTPException(status_code = 400, detail = "同一班级存在重叠的有效摄像设备绑定")


def _apply_binding(db, row, body):
	camera_id = _int(body, "camera_id", "摄像设备")
	class_id = _int(body, "class_id", "班级")
	_get(db, CameraDevice, camera_id, "摄像设备")
	_get(db, EduClass, class_id, "班级")
	start_date = _date(body, "effective_start_date", "生效开始日期")
	end_date = _date(body, "effective_end_date", "生效结束日期", required = False)
	if end_date and end_date <= start_date:
		raise HTTPException(status_code = 400, detail = "生效结束日期必须晚于开始日期")
	if _bool(body, "enabled", True):
		_check_binding_overlap(db, row, camera_id, class_id, start_date, end_date)
	row.camera_id = camera_id
	row.class_id = class_id
	row.effective_start_date = start_date
	row.effective_end_date = end_date
	row.enabled = 1 if _bool(body, "enabled", True) else 0
	row.remark = _text(body, "remark") or None


@router.get("/academic-years")
def academic_years(context = Depends(require_admin), db: Session = Depends(get_db)):
	rows = db.query(EduAcademicYear).order_by(EduAcademicYear.start_date.desc()).all()
	return { "ok": True, "items": [_serialize_year(row) for row in rows] }


@router.post("/academic-years")
async def create_academic_year(request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = EduAcademicYear()
	_apply_year(row, await request.json())
	db.add(row)
	db.commit()
	return { "ok": True, "item": _serialize_year(row) }


@router.put("/academic-years/{year_id}")
async def update_academic_year(year_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = _get(db, EduAcademicYear, year_id, "学年")
	_apply_year(row, await request.json())
	db.commit()
	return { "ok": True, "item": _serialize_year(row) }


@router.get("/academic-terms")
def academic_terms(context = Depends(require_admin), db: Session = Depends(get_db)):
	years = { row.id: row for row in db.query(EduAcademicYear).all() }
	rows = db.query(EduAcademicTerm).order_by(EduAcademicTerm.start_date.desc()).all()
	return { "ok": True, "items": [_serialize_term(row, years) for row in rows] }


@router.post("/academic-terms")
async def create_academic_term(request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = EduAcademicTerm()
	_apply_term(db, row, await request.json())
	db.add(row)
	db.commit()
	years = { item.id: item for item in db.query(EduAcademicYear).all() }
	return { "ok": True, "item": _serialize_term(row, years) }


@router.put("/academic-terms/{term_id}")
async def update_academic_term(term_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = _get(db, EduAcademicTerm, term_id, "学期")
	_apply_term(db, row, await request.json())
	db.commit()
	years = { item.id: item for item in db.query(EduAcademicYear).all() }
	return { "ok": True, "item": _serialize_term(row, years) }


@router.get("/subjects")
def subjects(context = Depends(require_admin), db: Session = Depends(get_db)):
	rows = db.query(EduSubject).filter(EduSubject.enabled == 1).order_by(EduSubject.subject_code.asc()).all()
	return { "ok": True, "items": [{ "id": row.id, "subject_code": row.subject_code, "subject_name": row.subject_name } for row in rows] }


@router.get("/teaching-courses")
def teaching_courses(context = Depends(require_admin), db: Session = Depends(get_db)):
	terms, classes, subjects, teachers = _course_options(db)
	rows = db.query(TeachingCourse).order_by(TeachingCourse.created_at.desc()).all()
	return { "ok": True, "items": [_serialize_course(row, terms, classes, subjects, teachers) for row in rows] }


@router.post("/teaching-courses")
async def create_teaching_course(request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = TeachingCourse()
	_apply_course(db, row, await request.json())
	if db.query(TeachingCourse).filter(TeachingCourse.course_no == row.course_no).first():
		raise HTTPException(status_code = 400, detail = "教学课程编号已存在")
	db.add(row)
	db.commit()
	terms, classes, subjects, teachers = _course_options(db)
	return { "ok": True, "item": _serialize_course(row, terms, classes, subjects, teachers) }


@router.put("/teaching-courses/{course_id}")
async def update_teaching_course(course_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = _get(db, TeachingCourse, course_id, "教学课程")
	_apply_course(db, row, await request.json())
	exists = db.query(TeachingCourse).filter(TeachingCourse.course_no == row.course_no, TeachingCourse.id != row.id).first()
	if exists:
		raise HTTPException(status_code = 400, detail = "教学课程编号已存在")
	_check_existing_course_schedules(db, row)
	db.commit()
	terms, classes, subjects, teachers = _course_options(db)
	return { "ok": True, "item": _serialize_course(row, terms, classes, subjects, teachers) }


@router.get("/schedules")
def schedules(
	teaching_course_id: int | None = Query(default = None),
	context = Depends(require_admin),
	db: Session = Depends(get_db),
):
	query = db.query(EduLessonSchedule)
	if teaching_course_id:
		query = query.filter(EduLessonSchedule.teaching_course_id == teaching_course_id)
	rows = query.order_by(EduLessonSchedule.weekday.asc(), EduLessonSchedule.start_time.asc()).all()
	return {
		"ok": True,
		"items": [
			{
				"id": row.id,
				"teaching_course_id": row.teaching_course_id,
				"weekday": row.weekday,
				"start_time": row.start_time,
				"end_time": row.end_time,
				"lesson_title": row.lesson_title or "",
				"enabled": bool(row.enabled),
			}
			for row in rows
		],
	}


@router.post("/schedules")
async def create_schedule(request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = EduLessonSchedule()
	_apply_schedule(db, row, await request.json())
	db.add(row)
	db.commit()
	return { "ok": True, "id": row.id }


@router.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = _get(db, EduLessonSchedule, schedule_id, "课表")
	_apply_schedule(db, row, await request.json())
	db.commit()
	return { "ok": True, "id": row.id }


@router.get("/cameras")
def cameras(context = Depends(require_admin), db: Session = Depends(get_db)):
	rows = db.query(CameraDevice).order_by(CameraDevice.device_code.asc()).all()
	return {
		"ok": True,
		"items": [
			{
				"id": row.id,
				"device_code": row.device_code,
				"device_name": row.device_name,
				"location": row.location or "",
				"source_path": row.source_path or "",
				"enabled": bool(row.enabled),
				"remark": row.remark or "",
			}
			for row in rows
		],
	}


@router.post("/cameras")
async def create_camera(request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = CameraDevice()
	_apply_camera(db, row, await request.json())
	db.add(row)
	db.commit()
	return { "ok": True, "id": row.id }


@router.put("/cameras/{camera_id}")
async def update_camera(camera_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = _get(db, CameraDevice, camera_id, "摄像设备")
	_apply_camera(db, row, await request.json())
	db.commit()
	return { "ok": True, "id": row.id }


@router.get("/camera-class-bindings")
def camera_class_bindings(context = Depends(require_admin), db: Session = Depends(get_db)):
	cameras_by_id = { row.id: row for row in db.query(CameraDevice).all() }
	classes_by_id = { row.id: row for row in db.query(EduClass).all() }
	rows = db.query(CameraClassBinding).order_by(CameraClassBinding.effective_start_date.desc()).all()
	return {
		"ok": True,
		"items": [
			{
				"id": row.id,
				"camera_id": row.camera_id,
				"camera_name": cameras_by_id.get(row.camera_id).device_name if cameras_by_id.get(row.camera_id) else "",
				"class_id": row.class_id,
				"class_name": classes_by_id.get(row.class_id).class_name if classes_by_id.get(row.class_id) else "",
				"effective_start_date": row.effective_start_date,
				"effective_end_date": row.effective_end_date,
				"enabled": bool(row.enabled),
				"remark": row.remark or "",
			}
			for row in rows
		],
	}


@router.post("/camera-class-bindings")
async def create_camera_class_binding(request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = CameraClassBinding()
	_apply_binding(db, row, await request.json())
	db.add(row)
	db.commit()
	return { "ok": True, "id": row.id }


@router.put("/camera-class-bindings/{binding_id}")
async def update_camera_class_binding(binding_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	row = _get(db, CameraClassBinding, binding_id, "摄像头班级绑定")
	_apply_binding(db, row, await request.json())
	db.commit()
	return { "ok": True, "id": row.id }
