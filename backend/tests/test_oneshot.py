"""בדיקות מצב ההרצה החד-פעמית (GitHub Actions): שמירת מצב בין הרצות, תזמון לא מדויק, תזכורות."""
from datetime import datetime, timedelta, timezone

import pytest
import respx
import httpx

from app import oneshot
from app.models import CheckRun, Event, Notification
from app.notifier import Notifier

T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


class Chan:
    name, configured = "Telegram", True

    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


def mock_pages():
    respx.get(url__regex=r".*/robots\.txt").mock(return_value=httpx.Response(404))
    respx.get("https://www.livenation.it/en/event/stray-kids-world-tour-run-it-milan--milano-tickets-edp1711785").mock(
        return_value=httpx.Response(200, text="<h1>[דמה] General Onsale — On sale soon</h1>"))
    respx.get("https://oasisinet.com/").mock(return_value=httpx.Response(200, text="<p>[דמה] TICKETS HAVE NOW SOLD OUT</p>"))
    respx.get(url__regex=r"https://app\.ticketmaster\.com/.*").mock(return_value=httpx.Response(200, json={}))


@pytest.mark.asyncio
@respx.mock
async def test_runs_every_5_minutes_even_if_slightly_early(db):
    mock_pages()
    ch = Chan()
    n = Notifier(senders=[ch])
    r1 = await oneshot.run(T0, n)
    assert len(r1["checked"]) == 1           # רק Oasis (Stray Kids נרכש — מעקב כבוי) # שתי ההופעות האמיתיות (הדמה כבויה)
    # GitHub הריץ 'מוקדם' ב-20 שניות — עדיין בודקים
    r2 = await oneshot.run(T0 + timedelta(minutes=5) - timedelta(seconds=20), n)
    assert len(r2["checked"]) == 1 and r2["skipped"] == []
    db.expire_all()
    assert db.query(CheckRun).filter(CheckRun.source_label == "Live Nation Italia").count() == 0
    assert db.query(CheckRun).filter(CheckRun.source_label == "oasisinet.com").count() == 2


@pytest.mark.asyncio
@respx.mock
async def test_state_unchanged_means_no_alerts(db):
    mock_pages()
    ch = Chan()
    n = Notifier(senders=[ch])
    await oneshot.run(T0, n)
    await oneshot.run(T0 + timedelta(minutes=5), n)
    db.expire_all()
    ev = db.query(Event).filter_by(slug="oasis-roma-2027").one()
    assert ev.status == "SOLD_OUT"
    # מצב שלא השתנה — אין התראות סטטוס (רק אולי מועד מכירה חדש)
    assert not [t for t in ch.sent if "אזל" in t.splitlines()[0]]


@pytest.mark.asyncio
@respx.mock
async def test_reminder_sent_by_oneshot(db):
    mock_pages()
    ch = Chan()
    skz = db.query(Event).filter_by(slug="stray-kids-milano-2027").one()
    skz.monitoring_enabled = True   # בודקים את מנגנון התזכורת
    db.commit()
    start = datetime.fromisoformat("2026-11-19T14:00:00+00:00")
    r = await oneshot.run(start - timedelta(minutes=12), Notifier(senders=[ch]))
    assert r["reminders"] == 1
    assert any("בעוד 15 דקות" in t for t in ch.sent)
    db.expire_all()
    assert db.query(Notification).filter_by(kind="reminder").count() == 1
