"""מתזמן: 'דופק' כל 5 שניות שמריץ הופעות שהגיע זמנן, ועבודת תחזוקה כל דקה."""
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import monitor
from .config import get_settings
from .db import SessionLocal
from .models import ErrorLog, Event
from .notifier import Notifier

log = logging.getLogger("scheduler")


class Engine:
    def __init__(self, notifier: Notifier | None = None, session_factory=SessionLocal):
        self.notifier = notifier or Notifier()
        self.session_factory = session_factory
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.lock = asyncio.Lock()
        self.last_tick: datetime | None = None
        self.last_maintenance: datetime | None = None
        self.client: httpx.AsyncClient | None = None

    def start(self):
        self.client = httpx.AsyncClient(timeout=20, headers={"User-Agent": get_settings().user_agent})
        self.scheduler.add_job(self.tick, "interval", seconds=5, id="tick", max_instances=1, coalesce=True)
        self.scheduler.add_job(self.maintenance, "interval", seconds=60, id="maint", max_instances=1, coalesce=True)
        self.scheduler.start()

    async def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        if self.client:
            await self.client.aclose()

    @property
    def running(self) -> bool:
        return self.scheduler.running

    async def tick(self):
        now = datetime.now(timezone.utc)
        self.last_tick = now
        if self.lock.locked():
            return
        async with self.lock:
            db = self.session_factory()
            try:
                due = [e for e in db.query(Event).filter(Event.monitoring_enabled.is_(True)).all()
                       if e.next_check_at is None or monitor.aware(e.next_check_at) <= now]
                for ev in due:
                    try:
                        await monitor.run_check(db, ev, self.client, self.notifier, now)
                    except Exception as e:  # noqa: BLE001 — תקלה בהופעה אחת לא מפילה את השאר
                        db.rollback()
                        log.exception("בדיקה נכשלה")
                        db.add(ErrorLog(event_id=ev.id, level="error", message=f"תקלה פנימית: {e}"[:1000]))
                        db.commit()
            finally:
                db.close()

    async def check_now(self, event_id: int) -> dict:
        async with self.lock:
            db = self.session_factory()
            try:
                ev = db.get(Event, event_id)
                client = self.client or httpx.AsyncClient(timeout=20)
                try:
                    return await monitor.run_check(db, ev, client, self.notifier)
                finally:
                    if client is not self.client:
                        await client.aclose()
            finally:
                db.close()

    async def maintenance(self):
        self.last_maintenance = datetime.now(timezone.utc)
        db = self.session_factory()
        try:
            await monitor.send_reminders(db, self.notifier)
            await monitor.health_check(db, self.notifier)
        except Exception:  # noqa: BLE001
            log.exception("תחזוקה נכשלה")
        finally:
            db.close()
