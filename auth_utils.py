from datetime import datetime, timedelta
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings


pwd_context = CryptContext(schemes = ["bcrypt"], deprecated = "auto")
MAX_BCRYPT_PASSWORD_BYTES = 72


def hash_password(password):
	if len(password.encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES:
		raise ValueError("密码 UTF-8 编码后不能超过 72 字节，请缩短 ADMIN_PASSWORD 或登录密码")
	return pwd_context.hash(password)


def verify_password(plain_password, password_hash):
	if not plain_password or not password_hash:
		return False
	if len(plain_password.encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES:
		return False
	return pwd_context.verify(plain_password, password_hash)


def create_access_token(subject, extra_claims = None, expires_delta = None):
	now = datetime.utcnow()
	expire = now + (expires_delta or timedelta(minutes = settings.access_token_expire_minutes))
	payload = {
		"sub": str(subject),
		"iat": int(now.timestamp()),
		"exp": expire,
		"jti": uuid4().hex,
		"type": "access",
	}
	if extra_claims:
		payload.update(extra_claims)
	return jwt.encode(payload, settings.jwt_secret_key, algorithm = settings.jwt_algorithm)


def create_refresh_token(subject, expires_delta = None):
	now = datetime.utcnow()
	expire = now + (expires_delta or timedelta(days = settings.refresh_token_expire_days))
	payload = {
		"sub": str(subject),
		"iat": int(now.timestamp()),
		"exp": expire,
		"jti": uuid4().hex,
		"type": "refresh",
	}
	return jwt.encode(payload, settings.jwt_secret_key, algorithm = settings.jwt_algorithm)


def decode_token(token):
	try:
		return jwt.decode(token, settings.jwt_secret_key, algorithms = [settings.jwt_algorithm])
	except JWTError:
		return None
