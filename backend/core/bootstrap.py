import logging

from core.auth_utils import hash_password
from core.config import settings
from core.database import db_session
from domain.models import SysRole, SysUser, SysUserRole


logger = logging.getLogger("monitor.bootstrap")


def bootstrap_admin_user():
	"""通过显式 ADMIN_PASSWORD 引导管理员账号，避免内置默认弱密码。"""
	if not settings.admin_password:
		return
	with db_session() as db:
		role = db.query(SysRole).filter(SysRole.role_code == "ADMIN").first()
		if not role:
			role = SysRole(role_code = "ADMIN", role_name = "系统管理员", description = "系统初始化管理员", enabled = 1)
			db.add(role)
			db.flush()

		user = db.query(SysUser).filter(SysUser.username == settings.admin_username).first()
		if not user:
			user = SysUser(
				username = settings.admin_username,
				password_hash = hash_password(settings.admin_password),
				real_name = "系统管理员",
				status = "ENABLED",
			)
			db.add(user)
			db.flush()
		else:
			user.password_hash = hash_password(settings.admin_password)
			user.status = "ENABLED"

		exists = db.query(SysUserRole).filter(SysUserRole.user_id == user.id, SysUserRole.role_id == role.id).first()
		if not exists:
			db.add(SysUserRole(user_id = user.id, role_id = role.id))
		logger.info("[Bootstrap] 管理员账号已初始化: %s", settings.admin_username)
