"""בדיקות API: הרשאות, הופעות, הצעות, תוכנית רכישה, הגדרות, מחיקת נתונים."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.scheduler import Engine
from app.notifier import Notifier


@pytest.fixture
def client(db, sender):
    app = create_app(engine=Engine(notifier=Notifier(sender=sender)), start_scheduler=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed(client):
    from app import auth
    auth._failed.clear()
    r = client.post("/api/login", json={"password": "test-password-123"})
    assert r.status_code == 200
    return client


def test_health_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_requires_login(client):
    assert client.get("/api/events").status_code == 401


def test_no_password_mode_only_for_local(client, monkeypatch):
    from app import auth
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "require_login", False)
    # TestClient מזדהה כ-"testclient" — כלומר לא מהמחשב עצמו: עדיין נדרשת סיסמה
    assert client.get("/api/events").status_code == 401
    assert client.get("/api/health").json()["login_required"] is True
    # גישה מהמחשב עצמו — בלי סיסמה
    monkeypatch.setattr(auth, "LOCAL_HOSTS", auth.LOCAL_HOSTS | {"testclient"})
    assert client.get("/api/events").status_code == 200
    assert client.get("/api/health").json()["login_required"] is False


def test_wrong_password_and_lockout(client):
    from app import auth
    auth._failed.clear()
    for _ in range(5):
        assert client.post("/api/login", json={"password": "nope"}).status_code == 401
    assert client.post("/api/login", json={"password": "test-password-123"}).status_code == 429
    auth._failed.clear()


def test_session_cookie_is_httponly(client):
    from app import auth
    auth._failed.clear()
    r = client.post("/api/login", json={"password": "test-password-123"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_seeded_events(authed):
    evs = {e["slug"]: e for e in authed.get("/api/events").json()}
    skz, oasis = evs["stray-kids-milano-2027"], evs["oasis-roma-2027"]
    assert skz["event_date"] == "2027-07-31" and skz["ticket_count"] == 4 and skz["max_total"] == 600
    assert skz["seating"] == "seated" and skz["allow_split"] is True
    verified = sorted(d["start_utc"] for d in skz["sale_dates"] if d["verified"])
    assert verified == ["2026-11-18T10:00:00+00:00", "2026-11-18T14:00:00+00:00", "2026-11-19T14:00:00+00:00"]
    assert oasis["event_date"] == "2027-07-29" and oasis["status"] == "SOLD_OUT"
    assert oasis["ticket_count"] == 2 and oasis["max_total"] == 300
    # מגבלת קצב: לא מתחת למה שהמכסה הרשמית מתירה
    tm = next(s for s in skz["sources"] if s["type"] == "ticketmaster_api")
    assert tm["min_interval"] >= 30


def test_add_event_without_code_change(authed):
    body = {"artist": "אמן חדש", "city": "Firenze", "event_date": "2027-06-01", "ticket_count": 2,
            "max_price_per_ticket": 100, "max_total": 200,
            "sources": [{"type": "page_watch", "label": "עמוד רשמי", "url": "https://example.com/e"}]}
    r = authed.post("/api/events", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "UNKNOWN"
    assert any(e["artist"] == "אמן חדש" for e in authed.get("/api/events").json())


def test_reject_bad_url(authed):
    r = authed.post("/api/events", json={"artist": "x", "city": "y", "official_url": "javascript:alert(1)"})
    assert r.status_code == 422


def test_toggle_monitoring(authed):
    eid = authed.get("/api/events").json()[0]["id"]
    assert authed.patch(f"/api/events/{eid}", json={"monitoring_enabled": False}).json()["monitoring_enabled"] is False
    assert authed.patch(f"/api/events/{eid}", json={"monitoring_enabled": True}).json()["monitoring_enabled"] is True


def test_manual_offer_and_ranking(authed):
    skz = next(e for e in authed.get("/api/events").json() if e["slug"] == "stray-kids-milano-2027")
    r = authed.post(f"/api/events/{skz['id']}/offers", json={
        "source": "ידני (בדיקה)", "section": "TEST", "row": "3", "seats": "1-4", "quantity": 4,
        "price_per_ticket": 140, "fees_included": True, "seated": True, "adjacent": True, "view_score": 4})
    assert r.status_code == 200
    assert r.json()["matches"][0]["section"] == "TEST"
    plan = authed.get(f"/api/events/{skz['id']}/purchase-plan").json()
    assert plan["mode"] == "manual_guided"
    assert plan["best"]["section"] == "TEST"
    assert any("עצור לפני תשלום" in s for s in plan["steps"])


def test_settings_and_budget(authed):
    s = authed.get("/api/settings").json()
    assert s["global_budget"] == 900 and s["budget"]["allocated"] == 900 and s["budget"]["ok"]
    s2 = authed.put("/api/settings", json={"global_budget": 850}).json()
    assert s2["budget"]["ok"] is False


def test_checklist(authed):
    items = authed.get("/api/checklist").json()["items"]
    assert any("SMS" in i["text"] for i in items)
    items[0]["done"] = True
    assert authed.put("/api/checklist", json={"items": items}).json()["items"][0]["done"] is True


def test_telegram_test_message(authed, sender):
    r = authed.post("/api/telegram/test").json()
    assert r["sent"] is True and "התראת בדיקה" in sender.sent[0]


def test_check_now_demo(authed, db):
    demo = next(e for e in authed.get("/api/events").json() if e["slug"] == "demo-event")
    r = authed.post(f"/api/events/{demo['id']}/check")
    assert r.status_code == 200 and r.json()["status"] == "NOT_ANNOUNCED"
    hist = authed.get(f"/api/events/{demo['id']}/history").json()
    assert hist and hist[0]["is_demo"] is True


def test_purge(authed, sender):
    authed.post("/api/telegram/test")
    assert authed.post("/api/data/purge", json={"scope": "history"}).json()["ok"]
    assert authed.get("/api/notifications").json() == []
    assert len(authed.get("/api/events").json()) >= 2
