import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
        if path not in ("", ":memory:"):
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    eng = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()
    return eng


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(eng=None):
    from . import models  # noqa: F401
    eng = eng or engine
    Base.metadata.create_all(eng)
    _migrate(eng)


def _migrate(eng):
    """הוספת עמודות חדשות לבסיס נתונים קיים (בלי למחוק נתונים)."""
    from sqlalchemy import inspect, text
    cols = {c["name"] for c in inspect(eng).get_columns("notifications")}
    if "channels_sent" not in cols:
        with eng.begin() as conn:
            conn.execute(text("ALTER TABLE notifications ADD COLUMN channels_sent JSON DEFAULT '[]'"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
