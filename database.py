from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings


engine = create_engine(
	settings.database_url,
	pool_pre_ping = True,
	pool_recycle = 3600,
	future = True,
)

SessionLocal = sessionmaker(bind = engine, autoflush = False, autocommit = False, future = True)
Base = declarative_base()


def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()


@contextmanager
def db_session():
	db = SessionLocal()
	try:
		yield db
		db.commit()
	except Exception:
		db.rollback()
		raise
	finally:
		db.close()


def init_database():
	"""仅在显式开启 AUTO_CREATE_TABLES 时自动建表；生产环境建议执行 db SQL 文件。"""
	if not settings.auto_create_tables:
		return
	import models  # noqa: F401

	Base.metadata.create_all(bind = engine)
