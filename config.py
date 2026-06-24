import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_PATH = Path(__file__).resolve().parent
load_dotenv(ROOT_PATH / ".env")


def _get_bool(name, default = False):
	value = os.environ.get(name)
	if value is None:
		return default
	return value.strip().lower() in { "1", "true", "yes", "on" }


@dataclass(frozen = True)
class AppConfig:
	"""应用运行配置，统一从环境变量读取，避免把敏感信息写入代码。"""
	database_url: str
	jwt_secret_key: str
	jwt_algorithm: str
	access_token_expire_minutes: int
	refresh_token_expire_days: int
	auto_create_tables: bool
	aliyun_api_key: str
	admin_username: str
	admin_password: str


def _build_database_url():
	database_url = os.environ.get("DATABASE_URL")
	if database_url:
		return database_url

	host = os.environ.get("MYSQL_HOST", "127.0.0.1")
	port = os.environ.get("MYSQL_PORT", "3306")
	user = os.environ.get("MYSQL_USER", "root")
	password = os.environ.get("MYSQL_PASSWORD", "")
	database = os.environ.get("MYSQL_DATABASE", "classroom_monitoring")
	charset = os.environ.get("MYSQL_CHARSET", "utf8mb4")
	return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"


def get_config():
	return AppConfig(
		database_url = _build_database_url(),
		jwt_secret_key = os.environ.get("JWT_SECRET_KEY", "please-change-this-secret"),
		jwt_algorithm = os.environ.get("JWT_ALGORITHM", "HS256"),
		access_token_expire_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "120")),
		refresh_token_expire_days = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "14")),
		auto_create_tables = _get_bool("AUTO_CREATE_TABLES", False),
		aliyun_api_key = os.environ.get("ALIYUN_API_KEY", ""),
		admin_username = os.environ.get("ADMIN_USERNAME", "admin"),
		admin_password = os.environ.get("ADMIN_PASSWORD", ""),
	)


settings = get_config()
