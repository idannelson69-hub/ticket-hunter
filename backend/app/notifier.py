"""התראות ל-Telegram ולמייל עם מניעת כפילויות (מפתח ייחודי בבסיס הנתונים)."""
import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Notification

log = logging.getLogger("notifier")

KIND_HE = {
    "announced": "📣 פורסמה הופעה רשמית",
    "sale_date": "🗓️ פורסם / עודכן מועד מכירה",
    "presale": "🔑 נפתחה מכירה מוקדמת",
    "on_sale": "🎟️ נפתחה מכירה",
    "match": "✅ נמצאו כרטיסים שעומדים בתנאים",
    "restock": "🔁 חזרה זמינות אחרי SOLD OUT",
    "sold_out": "⛔ אזל",
    "manual": "✋ נדרשת פעולה ידנית",
    "critical": "🚨 תקלה קריטית",
    "reminder": "⏰ תזכורת לפתיחת מכירה",
    "test": "🧪 התראת בדיקה",
}


class TelegramSender:
    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, chat_id

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send(self, text: str) -> None:
        if not self.configured:
            raise RuntimeError("Telegram לא מוגדר (חסר TELEGRAM_BOT_TOKEN או TELEGRAM_CHAT_ID)")
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        async with httpx.AsyncClient(timeout=15) as c:
            for attempt in range(3):
                r = await c.post(url, json=payload)
                if r.status_code == 429:
                    wait = (r.json().get("parameters") or {}).get("retry_after", 2)
                    await asyncio.sleep(min(int(wait), 30))
                    continue
                if r.status_code >= 400:
                    # לא מדפיסים את ה-URL — הוא מכיל את הטוקן
                    raise RuntimeError(f"Telegram החזיר שגיאה {r.status_code}: {r.json().get('description', '')}")
                return
        raise RuntimeError("Telegram: חריגה ממגבלת קצב גם אחרי ניסיונות חוזרים")

    name = "Telegram"


class EmailSender:
    """שליחת מייל ב-SMTP (למשל Gmail עם 'סיסמת אפליקציה'). הסיסמה רק במשתנה סביבה."""
    name = "מייל"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, to: str):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender = sender or user
        self.to = [x.strip() for x in (to or "").split(",") if x.strip()]

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.to)

    def _send_sync(self, text: str) -> None:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        first = text.splitlines()[0] if text else "התראה"
        msg["Subject"] = f"צייד כרטיסים: {first}"
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.to)
        msg.set_content(text + "\n\n— נשלח אוטומטית ממערכת צייד כרטיסים")
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=20) as s:
                s.login(self.user, self.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=20) as s:
                s.starttls()
                s.login(self.user, self.password)
                s.send_message(msg)

    async def send(self, text: str) -> None:
        if not self.configured:
            raise RuntimeError("מייל לא מוגדר (חסר SMTP_USER / SMTP_PASSWORD / EMAIL_TO)")
        try:
            await asyncio.to_thread(self._send_sync, text)
        except Exception as e:  # noqa: BLE001
            # לא מחזירים את הודעת השגיאה המלאה — היא עלולה לכלול פרטי התחברות
            raise RuntimeError(f"שליחת מייל נכשלה: {e.__class__.__name__}") from None


def default_senders() -> list:
    s = get_settings()
    return [TelegramSender(s.telegram_bot_token, s.telegram_chat_id),
            EmailSender(s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password, s.email_from, s.email_to)]


def fmt_local(dt_utc: datetime | None, tz: str = "Asia/Jerusalem") -> str:
    if not dt_utc:
        return "—"
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(ZoneInfo(tz)).strftime("%d.%m.%Y %H:%M")


def format_message(kind: str, event, *, site: str = "", price: str = "", link: str = "", details: str = "",
                   is_demo: bool = False, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    head = KIND_HE.get(kind, kind)
    if is_demo:
        head = "[דמה — לא נתון אמיתי] " + head
    lines = [head]
    if event is not None:
        date = event.event_date.strftime("%d.%m.%Y") if event.event_date else "לא ידוע"
        if event.event_date and not event.event_date_verified:
            date += " (לא אומת)"
        lines += [f"אמן: {event.artist}", f"עיר: {event.city}" + (f" · {event.venue}" if event.venue else ""),
                  f"תאריך הופעה: {date}", f"כרטיסים: {event.ticket_count}"]
    if site:
        lines.append(f"אתר: {site}")
    lines.append(f"מחיר: {price or 'לא ידוע'}")
    if details:
        lines.append(details)
    lines.append(f"שעה (ישראל): {fmt_local(now)}")
    lines.append(f"קישור: {link or (event.official_url if event is not None else '') or '—'}")
    return "\n".join(lines)


class Notifier:
    """שולח לכל הערוצים המוגדרים (Telegram + מייל). כל ערוץ נרשם בנפרד, כך שבשליחה חוזרת
    רק ערוץ שנכשל מקבל את ההודעה שוב — בלי כפילויות בערוץ שכבר הצליח."""

    def __init__(self, sender=None, senders: list | None = None):
        if senders is not None:
            self.senders = senders
        elif sender is not None:
            self.senders = [sender]
        else:
            self.senders = default_senders()

    def channels(self) -> list[dict]:
        return [{"name": getattr(s, "name", "בדיקה"), "configured": getattr(s, "configured", True)} for s in self.senders]

    async def notify(self, db: Session, kind: str, dedup_key: str, text: str, event_id: int | None = None,
                     is_demo: bool = False) -> Notification | None:
        """שולח פעם אחת בלבד לכל dedup_key. מחזיר None אם כבר נשלח."""
        key = dedup_key[:300]
        if db.query(Notification.id).filter_by(dedup_key=key).first():
            return None
        n = Notification(event_id=event_id, kind=kind, dedup_key=key, text=text, is_demo=is_demo)
        try:
            # SAVEPOINT: אם יש התנגשות, מבטלים רק את ההתראה ולא את שאר השינויים של הבדיקה
            with db.begin_nested():
                db.add(n)
                db.flush()
        except IntegrityError:
            return None
        db.commit()   # תופסים את המפתח לפני השליחה — כך גם קריסה באמצע לא תגרום לכפילות
        await self._deliver(db, n)
        return n

    async def _deliver(self, db: Session, n: Notification):
        done = list(n.channels_sent or [])
        errors = []
        active = [s for s in self.senders if getattr(s, "configured", True)]
        if not active:
            errors.append("לא הוגדר אף ערוץ התראה (Telegram או מייל)")
        for s in active:
            name = getattr(s, "name", "בדיקה")
            if name in done:
                continue
            try:
                await s.send(n.text)
                done.append(name)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e}")
        n.channels_sent = done
        n.sent = bool(active) and all(getattr(s, "name", "בדיקה") in done for s in active)
        n.error = " | ".join(errors)[:500]
        if errors:
            log.warning("שליחת התראה נכשלה: %s", n.error)
        db.commit()

    async def retry_unsent(self, db: Session, limit: int = 20, max_age_minutes: int = 60) -> int:
        """שליחה חוזרת רק להתראות מהשעה האחרונה — התראה ישנה כבר לא רלוונטית ולא תציף את הטלפון."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).replace(tzinfo=None)
        pending = (db.query(Notification).filter(Notification.sent.is_(False), Notification.created_at >= cutoff)
                   .order_by(Notification.id).limit(limit).all())
        for n in pending:
            await self._deliver(db, n)
        return sum(1 for n in pending if n.sent)
