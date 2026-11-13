"""הגדרת סביבת בדיקה: בסיס נתונים זמני, סודות דמה, טלגרם מזויף (לא נשלחת שום הודעה אמיתית)."""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="th-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "ADMIN_PASSWORD": "test-password-123",
    "SESSION_SECRET": "test-secret-0123456789abcdef",
    "SCHEDULER_ENABLED": "false",
    "DEMO_MODE": "true",
    "STATIC_DIR": os.path.join(_tmp, "no-static"),
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "TICKETMASTER_API_KEY": "TEST_KEY",
})
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.notifier import Notifier  # noqa: E402
from app.seed import seed  # noqa: E402


class FakeSender:
    """שולח מזויף: אוסף הודעות לרשימה. fail=True מדמה תקלה בטלגרם."""

    def __init__(self):
        self.sent: list[str] = []
        self.fail = False

    async def send(self, text: str):
        if self.fail:
            raise RuntimeError("תקלת רשת מדומה")
        self.sent.append(text)


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    init_db()
    s = SessionLocal()
    seed(s, demo=True)
    yield s
    s.close()


@pytest.fixture
def sender():
    return FakeSender()


@pytest.fixture
def notifier(sender):
    return Notifier(sender=sender)
