import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from auth_utils import create_access_token, create_refresh_token, decode_token, verify_password
from database import get_db
from dependencies import get_current_context
from models import EduTeacher, EduTeacherClass, SysAuthToken, SysLoginLog, SysRole, SysUser, SysUserRole


router = APIRouter(prefix = "/api/auth", tags = ["auth"])


def _client_ip(request):
	for header_name in ("x-forwarded-for", "x-real-ip"):
		value = request.headers.get(header_name)
		if value:
			return value.split(",")[0].strip()
	return request.client.host if request.client else ""


def _user_payload(db, user, roles = None):
	roles = roles or []
	teacher = db.query(EduTeacher).filter(EduTeacher.user_id == user.id).first()
	class_scopes = []
	if teacher:
		rows = db.query(EduTeacherClass).filter(EduTeacherClass.teacher_id == teacher.id, EduTeacherClass.enabled == 1).all()
		for row in rows:
			class_scopes.append(
				{
					"class_id": row.class_id,
					"subject_id": row.subject_id,
					"relation_type": row.relation_type,
					"can_view_monitor": bool(row.can_view_monitor),
					"can_start_monitor": bool(row.can_start_monitor),
					"can_review": bool(row.can_review),
				}
			)
	return {
		"id": user.id,
		"username": user.username,
		"real_name": user.real_name,
		"phone": user.phone,
		"email": user.email,
		"avatar_url": user.avatar_url,
		"roles": roles,
		"teacher": None if not teacher else {
			"id": teacher.id,
			"teacher_no": teacher.teacher_no,
			"teacher_name": teacher.teacher_name,
			"department": teacher.department,
			"title": teacher.title,
		},
		"class_scopes": class_scopes,
	}


def _write_login_log(db, user, username, result, reason, request):
	db.add(
		SysLoginLog(
			user_id = user.id if user else None,
			username = username or "",
			login_result = result,
			fail_reason = reason,
			client_ip = _client_ip(request),
			user_agent = request.headers.get("user-agent", ""),
		)
	)


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
	body = await request.json()
	username = (body or {}).get("username", "").strip()
	password = (body or {}).get("password", "")
	if not username or not password:
		raise HTTPException(status_code = 400, detail = "用户名和密码不能为空")

	user = db.query(SysUser).filter(SysUser.username == username).first()
	if not user:
		_write_login_log(db, None, username, "FAILED", "用户不存在", request)
		db.commit()
		raise HTTPException(status_code = 401, detail = "用户名或密码错误")
	if user.status != "ENABLED":
		_write_login_log(db, user, username, "LOCKED", "用户已禁用或锁定", request)
		db.commit()
		raise HTTPException(status_code = 403, detail = "用户已禁用或锁定")
	if not verify_password(password, user.password_hash):
		user.failed_login_count = (user.failed_login_count or 0) + 1
		_write_login_log(db, user, username, "FAILED", "密码错误", request)
		db.commit()
		raise HTTPException(status_code = 401, detail = "用户名或密码错误")

	user.failed_login_count = 0
	user.last_login_at = datetime.utcnow()
	user.last_login_ip = _client_ip(request)
	roles = [
		row[0]
		for row in (
			db.query(SysRole.role_code)
			.join(SysUserRole, SysUserRole.role_id == SysRole.id)
			.filter(SysUserRole.user_id == user.id, SysRole.enabled == 1)
			.all()
		)
	]
	access_token = create_access_token(user.id, { "roles": roles })
	refresh_token = create_refresh_token(user.id)
	access_payload = decode_token(access_token) or {}
	refresh_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
	db.add(
		SysAuthToken(
			user_id = user.id,
			token_jti = access_payload.get("jti", ""),
			refresh_token_hash = refresh_hash,
			client_ip = _client_ip(request),
			user_agent = request.headers.get("user-agent", ""),
			expires_at = datetime.utcfromtimestamp(access_payload["exp"]),
		)
	)
	_write_login_log(db, user, username, "SUCCESS", None, request)
	db.commit()
	return {
		"ok": True,
		"token_type": "Bearer",
		"access_token": access_token,
		"refresh_token": refresh_token,
		"user": _user_payload(db, user, roles),
	}


@router.post("/logout")
def logout(context = Depends(get_current_context), db: Session = Depends(get_db)):
	jti = context["payload"].get("jti")
	if jti:
		row = db.query(SysAuthToken).filter(SysAuthToken.token_jti == jti).first()
		if row and not row.revoked_at:
			row.revoked_at = datetime.utcnow()
			db.commit()
	return { "ok": True }


@router.post("/refresh")
def refresh_token(
	x_refresh_token = Header(default = None, alias = "X-Refresh-Token"),
	db: Session = Depends(get_db),
):
	if not x_refresh_token:
		raise HTTPException(status_code = 400, detail = "缺少 X-Refresh-Token 请求头")
	payload = decode_token(x_refresh_token)
	if not payload or payload.get("type") != "refresh":
		raise HTTPException(status_code = 401, detail = "refresh token 无效")
	refresh_hash = hashlib.sha256(x_refresh_token.encode("utf-8")).hexdigest()
	row = db.query(SysAuthToken).filter(SysAuthToken.refresh_token_hash == refresh_hash, SysAuthToken.revoked_at.is_(None)).first()
	if not row:
		raise HTTPException(status_code = 401, detail = "refresh token 已失效")
	user = db.query(SysUser).filter(SysUser.id == row.user_id, SysUser.status == "ENABLED").first()
	if not user:
		raise HTTPException(status_code = 401, detail = "用户不存在或已禁用")
	roles = [
		role[0]
		for role in (
			db.query(SysRole.role_code)
			.join(SysUserRole, SysUserRole.role_id == SysRole.id)
			.filter(SysUserRole.user_id == user.id, SysRole.enabled == 1)
			.all()
		)
	]
	access_token = create_access_token(user.id, { "roles": roles })
	access_payload = decode_token(access_token) or {}
	db.add(
		SysAuthToken(
			user_id = user.id,
			token_jti = access_payload.get("jti", ""),
			refresh_token_hash = refresh_hash,
			client_ip = row.client_ip,
			user_agent = row.user_agent,
			expires_at = datetime.utcfromtimestamp(access_payload["exp"]),
		)
	)
	db.commit()
	return { "ok": True, "token_type": "Bearer", "access_token": access_token }


@router.get("/me")
def me(context = Depends(get_current_context), db: Session = Depends(get_db)):
	return { "ok": True, "user": _user_payload(db, context["user"], context["roles"]) }
