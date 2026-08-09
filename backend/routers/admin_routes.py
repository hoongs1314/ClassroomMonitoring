from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.auth_utils import hash_password
from core.database import get_db
from core.dependencies import require_admin
from domain.models import EduClass, EduTeacher, EduTeacherClass, SysRole, SysUser, SysUserRole
from services.monitor_service import list_video_sources, refresh_runtime_class_config, state, validate_video_source


router = APIRouter(prefix = "/api/admin", tags = ["admin"])

ROLE_NAMES = {
	"ADMIN": "系统管理员",
	"TEACHER": "教师",
}
RELATION_TYPES = { "HEAD_TEACHER", "SUBJECT_TEACHER", "OBSERVER" }
USER_STATUSES = { "ENABLED", "DISABLED" }


def _text(body, key):
	return str((body or {}).get(key, "") or "").strip()


def _bool(body, key, default = False):
	value = (body or {}).get(key)
	return default if value is None else bool(value)


def _int(body, key):
	value = (body or {}).get(key)
	if value in (None, ""):
		return None
	try:
		return int(value)
	except (TypeError, ValueError):
		raise HTTPException(status_code = 400, detail = f"{key} 必须是整数")


def _require_text(body, key, title):
	value = _text(body, key)
	if not value:
		raise HTTPException(status_code = 400, detail = f"{title}不能为空")
	return value


def _ensure_role(db, role_code):
	role = db.query(SysRole).filter(SysRole.role_code == role_code).first()
	if role:
		return role
	role = SysRole(role_code = role_code, role_name = ROLE_NAMES[role_code], description = "管理员维护的系统角色", enabled = 1)
	db.add(role)
	db.flush()
	return role


def _role_codes_by_user(db):
	result = {}
	rows = db.query(SysUserRole.user_id, SysRole.role_code).join(SysRole, SysRole.id == SysUserRole.role_id).all()
	for user_id, role_code in rows:
		result.setdefault(user_id, []).append(role_code)
	return result


def _serialize_user(user, teacher, roles):
	return {
		"id": user.id,
		"username": user.username,
		"real_name": user.real_name,
		"phone": user.phone or "",
		"email": user.email or "",
		"status": user.status,
		"roles": roles,
		"role_code": "ADMIN" if "ADMIN" in roles else "TEACHER" if "TEACHER" in roles else "",
		"teacher": None if not teacher else {
			"id": teacher.id,
			"teacher_no": teacher.teacher_no,
			"teacher_name": teacher.teacher_name,
			"department": teacher.department or "",
			"title": teacher.title or "",
			"status": teacher.status,
		},
	}


def _get_class(db, class_id):
	row = db.query(EduClass).filter(EduClass.id == class_id).first()
	if not row:
		raise HTTPException(status_code = 404, detail = "班级不存在")
	return row


def _get_teacher(db, teacher_id):
	row = db.query(EduTeacher).filter(EduTeacher.id == teacher_id).first()
	if not row:
		raise HTTPException(status_code = 404, detail = "教师不存在")
	return row


def _serialize_class(row, teachers_by_id):
	head_teacher = teachers_by_id.get(row.head_teacher_id)
	return {
		"id": row.id,
		"class_code": row.class_code,
		"class_name": row.class_name,
		"grade_name": row.grade_name or "",
		"academic_year": row.academic_year or "",
		"default_video_path": row.default_video_path or "",
		"enabled": bool(row.enabled),
		"head_teacher_id": row.head_teacher_id,
		"head_teacher_name": head_teacher.teacher_name if head_teacher else "",
	}


def _check_class_identity(db, class_code, class_name, class_id = None):
	code_query = db.query(EduClass).filter(EduClass.class_code == class_code)
	name_query = db.query(EduClass).filter(EduClass.class_name == class_name)
	if class_id:
		code_query = code_query.filter(EduClass.id != class_id)
		name_query = name_query.filter(EduClass.id != class_id)
	if code_query.first():
		raise HTTPException(status_code = 400, detail = "班级编码已存在")
	if name_query.first():
		raise HTTPException(status_code = 400, detail = "班级名称已存在")


def _ensure_class_not_running(row):
	if state["is_running"] and state["current_class"] == row.class_name:
		raise HTTPException(status_code = 409, detail = "当前班级正在监控，请停止监控后再修改视频源、名称或启用状态")


def _apply_class_data(db, row, body):
	class_code = _require_text(body, "class_code", "班级编码")
	class_name = _require_text(body, "class_name", "班级名称")
	video_path = _text(body, "default_video_path")
	_check_class_identity(db, class_code, class_name, row.id)
	normalized_video_path = None
	if video_path:
		try:
			normalized_video_path = validate_video_source(video_path)
		except ValueError as exc:
			raise HTTPException(status_code = 400, detail = str(exc))

	head_teacher_id = _int(body, "head_teacher_id")
	if head_teacher_id is not None:
		_get_teacher(db, head_teacher_id)
	row.class_code = class_code
	row.class_name = class_name
	row.grade_name = _text(body, "grade_name") or None
	row.academic_year = _text(body, "academic_year") or None
	# 摄像设备成为正式视频来源；旧字段仅保留实时演示兼容，班级不再强制配置测试视频。
	if normalized_video_path:
		row.default_video_path = normalized_video_path
	elif not row.id:
		row.default_video_path = None
	row.enabled = 1 if _bool(body, "enabled", True) else 0
	row.head_teacher_id = head_teacher_id


@router.get("/video-sources")
def video_sources(context = Depends(require_admin)):
	return { "ok": True, "sources": list_video_sources() }


@router.get("/teachers")
def teachers(context = Depends(require_admin), db: Session = Depends(get_db)):
	rows = db.query(EduTeacher).order_by(EduTeacher.teacher_no.asc()).all()
	return {
		"ok": True,
		"teachers": [
			{
				"id": row.id,
				"teacher_no": row.teacher_no,
				"teacher_name": row.teacher_name,
				"status": row.status,
			}
			for row in rows
		],
	}


@router.get("/users")
def users(context = Depends(require_admin), db: Session = Depends(get_db)):
	role_codes = _role_codes_by_user(db)
	teachers_by_user_id = { row.user_id: row for row in db.query(EduTeacher).all() if row.user_id }
	rows = db.query(SysUser).order_by(SysUser.id.desc()).all()
	return {
		"ok": True,
		"users": [
			_serialize_user(row, teachers_by_user_id.get(row.id), role_codes.get(row.id, []))
			for row in rows
		],
	}


@router.post("/users")
async def create_user(request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	body = await request.json()
	username = _require_text(body, "username", "用户名")
	password = _require_text(body, "password", "初始密码")
	real_name = _require_text(body, "real_name", "姓名")
	role_code = _text(body, "role_code").upper() or "TEACHER"
	status = _text(body, "status").upper() or "ENABLED"
	if role_code not in ROLE_NAMES:
		raise HTTPException(status_code = 400, detail = "账号角色仅支持系统管理员或教师")
	if status not in USER_STATUSES:
		raise HTTPException(status_code = 400, detail = "账号状态无效")
	if len(password) < 8:
		raise HTTPException(status_code = 400, detail = "初始密码至少需要 8 位")
	if db.query(SysUser).filter(SysUser.username == username).first():
		raise HTTPException(status_code = 400, detail = "用户名已存在")

	try:
		user = SysUser(
			username = username,
			password_hash = hash_password(password),
			real_name = real_name,
			phone = _text(body, "phone") or None,
			email = _text(body, "email") or None,
			status = status,
			password_changed_at = datetime.utcnow(),
		)
	except ValueError as exc:
		raise HTTPException(status_code = 400, detail = str(exc))
	db.add(user)
	db.flush()
	role = _ensure_role(db, role_code)
	db.add(SysUserRole(user_id = user.id, role_id = role.id))

	teacher = None
	if role_code == "TEACHER":
		teacher_no = _require_text(body, "teacher_no", "教师编号")
		if db.query(EduTeacher).filter(EduTeacher.teacher_no == teacher_no).first():
			raise HTTPException(status_code = 400, detail = "教师编号已存在")
		teacher = EduTeacher(
			user_id = user.id,
			teacher_no = teacher_no,
			teacher_name = _text(body, "teacher_name") or real_name,
			phone = user.phone,
			email = user.email,
			department = _text(body, "department") or None,
			title = _text(body, "title") or None,
			status = status,
		)
		db.add(teacher)
	db.flush()
	db.commit()
	return { "ok": True, "user": _serialize_user(user, teacher, [role_code]) }


@router.put("/users/{user_id}")
async def update_user(user_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	body = await request.json()
	user = db.query(SysUser).filter(SysUser.id == user_id).first()
	if not user:
		raise HTTPException(status_code = 404, detail = "账号不存在")
	status = _text(body, "status").upper() or user.status
	if status not in USER_STATUSES:
		raise HTTPException(status_code = 400, detail = "账号状态无效")
	if user.id == context["user"].id and status != "ENABLED":
		raise HTTPException(status_code = 400, detail = "不能禁用当前登录账号")

	user.real_name = _require_text(body, "real_name", "姓名")
	user.phone = _text(body, "phone") or None
	user.email = _text(body, "email") or None
	user.status = status
	password = _text(body, "password")
	if password:
		if len(password) < 8:
			raise HTTPException(status_code = 400, detail = "新密码至少需要 8 位")
		try:
			user.password_hash = hash_password(password)
		except ValueError as exc:
			raise HTTPException(status_code = 400, detail = str(exc))
		user.password_changed_at = datetime.utcnow()

	teacher = db.query(EduTeacher).filter(EduTeacher.user_id == user.id).first()
	if teacher:
		teacher_no = _require_text(body, "teacher_no", "教师编号")
		exists = db.query(EduTeacher).filter(EduTeacher.teacher_no == teacher_no, EduTeacher.id != teacher.id).first()
		if exists:
			raise HTTPException(status_code = 400, detail = "教师编号已存在")
		teacher.teacher_no = teacher_no
		teacher.teacher_name = _text(body, "teacher_name") or user.real_name
		teacher.phone = user.phone
		teacher.email = user.email
		teacher.department = _text(body, "department") or None
		teacher.title = _text(body, "title") or None
		teacher.status = status

	db.commit()
	roles = _role_codes_by_user(db).get(user.id, [])
	return { "ok": True, "user": _serialize_user(user, teacher, roles) }


@router.get("/classes")
def classes(context = Depends(require_admin), db: Session = Depends(get_db)):
	teachers_by_id = { row.id: row for row in db.query(EduTeacher).all() }
	rows = db.query(EduClass).order_by(EduClass.class_code.asc()).all()
	return { "ok": True, "classes": [_serialize_class(row, teachers_by_id) for row in rows] }


@router.post("/classes")
async def create_class(request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	body = await request.json()
	row = EduClass()
	_apply_class_data(db, row, body)
	db.add(row)
	db.commit()
	refresh_runtime_class_config()
	teachers_by_id = { teacher.id: teacher for teacher in db.query(EduTeacher).all() }
	return { "ok": True, "class": _serialize_class(row, teachers_by_id) }


@router.put("/classes/{class_id}")
async def update_class(class_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	body = await request.json()
	row = _get_class(db, class_id)
	_ensure_class_not_running(row)
	_apply_class_data(db, row, body)
	db.commit()
	refresh_runtime_class_config()
	teachers_by_id = { teacher.id: teacher for teacher in db.query(EduTeacher).all() }
	return { "ok": True, "class": _serialize_class(row, teachers_by_id) }


def _serialize_scope(row):
	return {
		"id": row.id,
		"teacher_id": row.teacher_id,
		"teacher_no": row.teacher.teacher_no,
		"teacher_name": row.teacher.teacher_name,
		"relation_type": row.relation_type,
		"can_view_monitor": bool(row.can_view_monitor),
		"can_start_monitor": bool(row.can_start_monitor),
		"can_review": bool(row.can_review),
		"enabled": bool(row.enabled),
	}


def _apply_scope_data(row, body):
	relation_type = _text(body, "relation_type").upper() or "SUBJECT_TEACHER"
	if relation_type not in RELATION_TYPES:
		raise HTTPException(status_code = 400, detail = "教师班级关系无效")
	row.relation_type = relation_type
	row.can_view_monitor = 1 if _bool(body, "can_view_monitor", True) else 0
	row.can_start_monitor = 1 if _bool(body, "can_start_monitor", False) else 0
	row.can_review = 1 if _bool(body, "can_review", True) else 0
	row.enabled = 1 if _bool(body, "enabled", True) else 0


@router.get("/classes/{class_id}/scopes")
def class_scopes(class_id: int, context = Depends(require_admin), db: Session = Depends(get_db)):
	_get_class(db, class_id)
	rows = (
		db.query(EduTeacherClass)
		.filter(EduTeacherClass.class_id == class_id)
		.order_by(EduTeacherClass.id.desc())
		.all()
	)
	return { "ok": True, "scopes": [_serialize_scope(row) for row in rows] }


@router.post("/classes/{class_id}/scopes")
async def save_class_scope(class_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	body = await request.json()
	_get_class(db, class_id)
	teacher_id = _int(body, "teacher_id")
	if teacher_id is None:
		raise HTTPException(status_code = 400, detail = "请选择教师")
	_get_teacher(db, teacher_id)
	row = (
		db.query(EduTeacherClass)
		.filter(EduTeacherClass.class_id == class_id, EduTeacherClass.teacher_id == teacher_id)
		.order_by(EduTeacherClass.id.asc())
		.first()
	)
	if not row:
		row = EduTeacherClass(teacher_id = teacher_id, class_id = class_id, relation_type = "SUBJECT_TEACHER")
		db.add(row)
	_apply_scope_data(row, body)
	db.commit()
	return { "ok": True, "scope": _serialize_scope(row) }


@router.put("/class-scopes/{scope_id}")
async def update_class_scope(scope_id: int, request: Request, context = Depends(require_admin), db: Session = Depends(get_db)):
	body = await request.json()
	row = db.query(EduTeacherClass).filter(EduTeacherClass.id == scope_id).first()
	if not row:
		raise HTTPException(status_code = 404, detail = "授权记录不存在")
	_apply_scope_data(row, body)
	db.commit()
	return { "ok": True, "scope": _serialize_scope(row) }
