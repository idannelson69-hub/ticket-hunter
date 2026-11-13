"""סימולציות מנוע הניטור: פתיחת מכירה, SOLD OUT וחזרת מלאי, תקלות והתאוששות, תזכורות וכפילויות.
כל הנתונים כאן מסומנים כדמה."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app import monitor
from app.models import ErrorLog, Event, Notification, Offer
from app.sources import ticketmaster

T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def demo_event(db):
    ev = db.query(Event).filter_by(slug="demo-event").one()
    ev.monitoring_enabled = True
    db.commit()
    return ev


async def run_steps(db, ev, notifier, n, start=T0, step=timedelta(seconds=30)):
    out = []
    async with httpx.AsyncClient() as c:
        for i in range(n):
            out.append(await monitor.run_check(db, ev, c, notifier, start + step * i))
    return out


@pytest.mark.asyncio
async def test_full_sale_simulation(db, notifier, sender):
    """טרם הוכרזה → הוכרזה → מוקדמת → זמין → אזל → חזרת מלאי."""
    ev = demo_event(db)
    res = await run_steps(db, ev, notifier, 6)
    statuses = [r["status"] for r in res]
    assert statuses == ["NOT_ANNOUNCED", "ANNOUNCED", "PRESALE", "AVAILABLE", "SOLD_OUT", "AVAILABLE"]
    kinds = [n.kind for n in db.query(Notification).order_by(Notification.id)]
    assert "announced" in kinds and "sale_date" in kinds and "presale" in kinds
    assert "on_sale" in kinds and "sold_out" in kinds and "restock" in kinds and "match" in kinds
    # כל הודעה מסומנת כדמה
    assert all(t.startswith("[דמה") for t in sender.sent)
    assert all(n.is_demo for n in db.query(Notification))


@pytest.mark.asyncio
async def test_match_notification_contents(db, notifier, sender):
    ev = demo_event(db)
    await run_steps(db, ev, notifier, 4)
    match = [t for t in sender.sent if "נמצאו כרטיסים" in t]
    assert match, "חייבת להישלח התראת התאמה"
    m = match[0]
    for needed in ("אמן:", "עיר:", "תאריך הופעה:", "כרטיסים: 4", "מחיר:", "שעה (ישראל):", "קישור:", "אתר:"):
        assert needed in m
    assert "DEMO-A1" in m           # ההצעה הטובה בתקציב
    assert "DEMO-VIP" not in "".join(match)   # מעל התקציב
    assert "DEMO-B3" not in "".join(match)    # ראות מוגבלת


@pytest.mark.asyncio
async def test_no_duplicate_notifications_on_repeat(db, notifier, sender):
    ev = demo_event(db)
    await run_steps(db, ev, notifier, 4)
    before = len(sender.sent)
    # הצעד האחרון בתרחיש חוזר על עצמו (AVAILABLE) — אסור שיישלחו שוב אותן התראות
    ev.sources_state["מקור דמה"]["step"] = 99   # נתקע על הצעד האחרון (AVAILABLE) — אותו מצב שוב ושוב
    ev.sources_state = dict(ev.sources_state)
    db.commit()
    await run_steps(db, ev, notifier, 3, start=T0 + timedelta(hours=1))
    assert len(sender.sent) == before


@pytest.mark.asyncio
async def test_dedup_key_unique(db, notifier, sender):
    a = await notifier.notify(db, "test", "same-key", "הודעה 1")
    b = await notifier.notify(db, "test", "same-key", "הודעה 2")
    assert a is not None and b is None and sender.sent == ["הודעה 1"]


@pytest.mark.asyncio
async def test_restock_alerts_each_cycle(db, notifier, sender):
    ev = demo_event(db)
    ev.sources = [{"type": "demo", "label": "מקור דמה", "enabled": True,
                   "scenario": ["SOLD_OUT", "ON_SALE", "SOLD_OUT", "ON_SALE"]}]
    db.commit()
    await run_steps(db, ev, notifier, 4)
    kinds = [n.kind for n in db.query(Notification).filter(Notification.kind.in_(["restock", "sold_out"]))
             .order_by(Notification.id)]
    assert kinds == ["sold_out", "restock", "sold_out", "restock"]


def tm_only(db, slug="stray-kids-milano-2027"):
    ev = db.query(Event).filter_by(slug=slug).one()
    ev.sources = [{"type": "ticketmaster_api", "label": "Ticketmaster API", "keyword": "Stray Kids"}]
    ev.sources_state = {}
    db.commit()
    return ev


@pytest.mark.asyncio
@respx.mock
async def test_failure_backoff_critical_and_recovery(db, notifier, sender):
    ev = tm_only(db)
    route = respx.get(f"{ticketmaster.BASE}/events.json")
    route.mock(return_value=httpx.Response(500))
    t = T0
    gaps = []
    async with httpx.AsyncClient() as c:
        for _ in range(5):
            await monitor.run_check(db, ev, c, notifier, t)
            nxt = datetime.fromisoformat(ev.sources_state["Ticketmaster API"]["next_allowed"])
            gaps.append(int((nxt - t).total_seconds()))
            t = nxt + timedelta(seconds=1)   # מכבדים את ה-backoff
        assert ev.consecutive_failures == 5
        assert db.query(Notification).filter_by(kind="critical").count() == 1
        assert db.query(ErrorLog).count() == 5
        # backoff גדל אקספוננציאלית ומוגבל לשעה
        assert gaps == [600, 1200, 2400, 3600, 3600]

        # בתוך זמן ההמתנה המקור לא נבדק בכלל
        calls = route.call_count
        await monitor.run_check(db, ev, c, notifier, t - timedelta(seconds=10))
        assert route.call_count == calls

        # התאוששות
        route.mock(return_value=httpx.Response(200, json={"_embedded": {"events": [{
            "id": "X", "name": "[דמה]", "url": "https://www.ticketmaster.it/event/DEMO",
            "dates": {"status": {"code": "onsale"}}, "sales": {"public": {"startDateTime": "2026-11-19T14:00:00Z"}}}]}}))
        await monitor.run_check(db, ev, c, notifier, t)
    assert ev.consecutive_failures == 0
    assert ev.sources_state["Ticketmaster API"]["failures"] == 0
    assert ev.sources[0]["external_id"] == "X"


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_retry_after_respected(db, notifier):
    ev = tm_only(db)
    respx.get(f"{ticketmaster.BASE}/events.json").mock(return_value=httpx.Response(429, headers={"Retry-After": "900"}))
    async with httpx.AsyncClient() as c:
        await monitor.run_check(db, ev, c, notifier, T0)
    nxt = datetime.fromisoformat(ev.sources_state["Ticketmaster API"]["next_allowed"])
    assert (nxt - T0).total_seconds() == 900


@pytest.mark.asyncio
@respx.mock
async def test_sale_date_change_detected(db, notifier, sender):
    ev = tm_only(db)
    body = lambda ts: {"_embedded": {"events": [{"id": "X", "name": "[דמה]", "dates": {"status": {"code": "offsale"}},
                                                  "sales": {"public": {"startDateTime": ts}}}]}}
    route = respx.get(f"{ticketmaster.BASE}/events.json")
    route.mock(return_value=httpx.Response(200, json=body("2026-11-19T14:00:00Z")))
    async with httpx.AsyncClient() as c:
        await monitor.run_check(db, ev, c, notifier, T0)
        n1 = db.query(Notification).filter_by(kind="sale_date").count()
        respx.get(f"{ticketmaster.BASE}/events/X.json").mock(
            return_value=httpx.Response(200, json=body("2026-11-20T14:00:00Z")["_embedded"]["events"][0]))
        await monitor.run_check(db, ev, c, notifier, T0 + timedelta(hours=1))
    assert db.query(Notification).filter_by(kind="sale_date").count() == n1 + 1
    names = [d["start_utc"] for d in ev.sale_dates if d["source"] == "Ticketmaster API"]
    assert names == ["2026-11-20T14:00:00+00:00"]


@pytest.mark.asyncio
async def test_reminders_tiers_only_verified(db, notifier, sender):
    ev = db.query(Event).filter_by(slug="stray-kids-milano-2027").one()
    start = datetime.fromisoformat("2026-11-19T14:00:00+00:00")
    # 23 שעות לפני — תזכורת 24 שעות בלבד
    assert await monitor.send_reminders(db, notifier, start - timedelta(hours=23)) == 1
    assert await monitor.send_reminders(db, notifier, start - timedelta(hours=22)) == 0   # בלי כפילות
    # 50 דקות לפני — תזכורת שעה
    assert await monitor.send_reminders(db, notifier, start - timedelta(minutes=50)) == 1
    # 10 דקות לפני — תזכורת 15 דקות
    assert await monitor.send_reminders(db, notifier, start - timedelta(minutes=10)) == 1
    assert await monitor.send_reminders(db, notifier, start + timedelta(minutes=1)) == 0
    # מועדי ה-Presale שלא אומתו (18.11) לא מייצרים תזכורות
    assert all("Presale" not in t for t in sender.sent)


@pytest.mark.asyncio
async def test_reminder_late_start_skips_old_tiers(db, notifier, sender):
    """אם השרת עלה 30 דקות לפני — לא שולחים תזכורת '24 שעות' באיחור."""
    start = datetime.fromisoformat("2026-11-19T14:00:00+00:00")
    await monitor.send_reminders(db, notifier, start - timedelta(minutes=30))
    assert len(sender.sent) == 1 and "בעוד שעה" in sender.sent[0]


@pytest.mark.asyncio
async def test_telegram_failure_is_recorded_and_retried(db, notifier, sender):
    sender.fail = True
    n = await notifier.notify(db, "test", "k1", "שלום")
    assert n.sent is False and "מדומה" in n.error
    sender.fail = False
    assert await notifier.retry_unsent(db) == 1
    assert sender.sent == ["שלום"]


@pytest.mark.asyncio
async def test_health_check_detects_stalled_monitor(db, notifier, sender):
    ev = db.query(Event).filter_by(slug="oasis-roma-2027").one()
    ev.last_check_at = (T0 - timedelta(hours=2)).replace(tzinfo=None)
    db.commit()
    stale = await monitor.health_check(db, notifier, T0)
    assert "oasis-roma-2027" in stale
    assert any("תקלה קריטית" in t for t in sender.sent)


@pytest.mark.asyncio
async def test_manual_offer_not_removed_by_monitor(db, notifier):
    ev = demo_event(db)
    db.add(Offer(event_id=ev.id, source="ידני", quantity=4, price_per_ticket=100, seated=True, adjacent=True))
    db.commit()
    await run_steps(db, ev, notifier, 6)
    assert db.query(Offer).filter_by(source="ידני", active=True).count() == 1
