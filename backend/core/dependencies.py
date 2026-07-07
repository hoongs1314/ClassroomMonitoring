from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from core.auth_utils import decode_token
from core.database import get_db
from domain.models import EduTeacher, SysAuthToken, SysRole, SysUser, SysUserRole


def parse_header_int(value, name, required = False):
	if value in (None, ""):
		if required:
			raise HTTPException(status_code = 400, detail = f"缺少请求头 {name}")
		return None
	try:
		return int(value)
	except ValueError:
		raise HTTPException(status_code = 400, detail = f"请求头 {name} 必须是整数")


def parse_bearer_token(authorization):
	if not authorization:
		raise HTTPException(status_code = 401, detail = "缺少 Authorization 请求头")
	parts = authorization.split(" ", 1)
	if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
		raise HTTPException(status_code = 401, detail = "Authorization 格式应为 Bearer token")
	return parts[1].strip()


def get_bearer_token(authorization = Header(default = None, alias = "Authorization")):
	return parse_bearer_token(authorization)


def _load_roles(db, user_id):
	rows = (
		db.query(SysRole.role_code)
		.join(SysUserRole, SysUserRole.role_id == SysRole.id)
		.filter(SysUserRole.user_id == user_id, SysRole.enabled == 1)
		.all()
	)
	return [row[0] for row in rows]


def load_context_from_token(db, token):
	payload = decode_token(token)
	if not payload or payload.get("type") != "access":
		raise HTTPException(status_code = 401, detail = "登录状态无效或已过期")

	user_id = parse_header_int(payload.get("sub"), "token.sub", required = True)
	user = db.query(SysUser).filter(SysUser.id == user_id).first()
	if not user or user.status != "ENABLED":
		raise HTTPException(status_code = 401, detail = "用户不存在或已被禁用")

	jti = payload.get("jti")
	if jti:
		token_row = db.query(SysAuthToken).filter(SysAuthToken.token_jti == jti).first()
		if token_row and token_row.revoked_at is not None:
			raise HTTPException(status_code = 401, detail = "登录状态已失效")

	roles = _load_roles(db, user.id)
	teacher = db.query(EduTeacher).filter(EduTeacher.user_id == user.id).first()
	return { "user": user, "roles": roles, "teacher": teacher, "payload": payload, "token": token }


def get_current_context(
	db: Session = Depends(get_db),
	token = Depends(get_bearer_token),
):
	return load_context_from_token(db, token)


def require_admin(context = Depends(get_current_context)):
	if "ADMIN" not in context["roles"]:
		raise HTTPException(status_code = 403, detail = "需要管理员权限")
	return context


def is_admin(context):
	return "ADMIN" in context.get("roles", [])
