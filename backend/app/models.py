from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Event(Base):
    """הופעה במעקב. כל ההגדרות נשמרות כאן כך שאפשר להוסיף הופעות בלי לשנות קוד."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    artist: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    venue: Mapped[str] = mapped_column(String(120), default="")
    event_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    event_date_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_note: Mapped[str] = mapped_column(Text, default="")
    official_url: Mapped[str] = mapped_column(String(500), default="")

    # העדפות רכישה
    ticket_count: Mapped[int] = mapped_column(Integer, default=2)
    max_price_per_ticket: Mapped[float] = mapped_column(Float, default=150.0)  # כולל עמלות
    max_total: Mapped[float] = mapped_column(Float, default=300.0)             # כולל עמלות
    seating: Mapped[str] = mapped_column(String(20), default="any")           # seated / standing / any
    require_adjacent: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_split: Mapped[bool] = mapped_column(Boolean, default=False)         # 2+2 באישור
    allow_restricted_view: Mapped[bool] = mapped_column(Boolean, default=False)

    # ניטור
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    sources: Mapped[list] = mapped_column(JSON, default=list)        # [{type,label,url,keyword,...}]
    sources_state: Mapped[dict] = mapped_column(JSON, default=dict)  # כשלונות/המתנה לכל מקור
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sale_dates: Mapped[list] = mapped_column(JSON, default=list)    # [{name,start_utc,verified,source}]
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CheckRun(Base):
    """היסטוריית בדיקות."""
    __tablename__ = "check_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    source_label: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Offer(Base):
    """הצעת כרטיסים (מהזנה ידנית או ממקור דמה). אין כאן שום פרט תשלום."""
    __tablename__ = "offers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(80), default="ידני")
    url: Mapped[str] = mapped_column(String(500), default="")
    section: Mapped[str] = mapped_column(String(80), default="")
    row: Mapped[str] = mapped_column(String(40), default="")
    seats: Mapped[str] = mapped_column(String(120), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price_per_ticket: Mapped[float] = mapped_column(Float)
    fees_included: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    seated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    adjacent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    view_score: Mapped[int | None] = mapped_column(Integer, nullable=True)       # 1–5
    restricted_view: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    location_score: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 1–5
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    found_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Notification(Base):
    """היסטוריית התראות. dedup_key ייחודי = מניעת כפילויות גם אחרי הפעלה מחדש."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    dedup_key: Mapped[str] = mapped_column(String(300), unique=True)
    text: Mapped[str] = mapped_column(Text)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    channels_sent: Mapped[list] = mapped_column(JSON, default=list)   # ["Telegram", "מייל"]
    error: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ErrorLog(Base):
    __tablename__ = "error_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_label: Mapped[str] = mapped_column(String(120), default="")
    level: Mapped[str] = mapped_column(String(20), default="error")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AuditLog(Base):
    """לוג פעולות משתמש — ללא פרטים רגישים."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KV(Base):
    """הגדרות משתמש כלליות (תקציב כולל, רשימת בדיקות וכו')."""
    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
