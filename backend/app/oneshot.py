"""הרצה חד-פעמית: סבב בדיקה אחד לכל ההופעות, תזכורות ושליחה חוזרת — ואז יציאה.

משמש את GitHub Actions (כל ~5 דקות). המצב (בסיס הנתונים) נשמר בין הרצות ב-cache של GitHub.
הפעלה:  python -m app.oneshot
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

import httpx

from . import monitor
from .config import get_settings
from .db import SessionLocal, init_db
from .models import ErrorLog, Event
from .notifier import Notifier
from .seed import seed

log = logging.getLogger("oneshot")
TOLERANCE = 150   # שניות: GitHub מריץ לפי לוח זמנים לא מדויק


async def run(now: datetime | None = None, notifier: Notifier | None = None) -> dict:
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    init_db()
    db = SessionLocal()
    notifier = notifier or Notifier()
    out = {"checked": [], "skipped": [], "errors": 0, "reminders": 0, "channels": notifier.channels()}
    try:
        seed(db, demo=s.demo_mode)
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": s.user_agent}) as client:
            for ev in db.query(Event).filter(Event.monitoring_enabled.is_(True)).all():
                due = ev.next_check_at is None or monitor.aware(ev.next_check_at) <= now + timedelta(seconds=TOLERANCE)
                if not due:
                    out["skipped"].append(ev.slug)
                    continue
                try:
                    r = await monitor.run_check(db, ev, client, notifier, now, tolerance_seconds=TOLERANCE)
                    out["checked"].append(f"{ev.slug}: {r['status']} ({r['results']}/{r['attempted']} מקורות) {r['notifications']}")
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    out["errors"] += 1
                    db.add(ErrorLog(event_id=ev.id, level="error", message=f"תקלה פנימית: {e}"[:1000]))
                    db.commit()
        out["reminders"] = await monitor.send_reminders(db, notifier, now)
        await notifier.retry_unsent(db)
    finally:
        db.close()
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    out = asyncio.run(run())
    print("ערוצים:", ", ".join(f"{c['name']}={'מחובר' if c['configured'] else 'לא מחובר'}" for c in out["channels"]))
    for line in out["checked"]:
        print("✓", line)
    for slug in out["skipped"]:
        print("· עוד לא הגיע הזמן:", slug)
    print("תזכורות שנשלחו:", out["reminders"])
    return 1 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
