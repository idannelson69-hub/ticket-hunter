"""בדיקות מקורות: Ticketmaster Discovery API (מדומה עם respx) ומעקב עמודים. אין פנייה אמיתית לאינטרנט."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
import respx

from app.sources import pagewatch, ticketmaster
from app.sources.base import SourceError
from app.statuses import Status, combine

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
EV = SimpleNamespace(artist="Stray Kids", event_date=date(2027, 7, 31))


def tm_event(code="onsale", public="2026-11-19T14:00:00Z", presales=None, **kw):
    return {"id": "TMDEMO1", "name": "[דמה] Stray Kids", "url": "https://www.ticketmaster.it/event/DEMO",
            "dates": {"status": {"code": code}}, "sales": {"public": {"startDateTime": public},
                                                           "presales": presales or []},
            "_embedded": {"venues": [{"name": "Stadio San Siro"}]}, **kw}


def test_interpret_announced_before_public_sale():
    r = ticketmaster.interpret(tm_event(), NOW)
    assert r.status == Status.ANNOUNCED
    assert r.sale_dates[0].name == "מכירה כללית" and r.sale_dates[0].verified


def test_interpret_presale_active():
    pres = [{"name": "STAY Presale", "startDateTime": "2026-11-13T10:00:00Z", "endDateTime": "2026-11-14T10:00:00Z"}]
    assert ticketmaster.interpret(tm_event(presales=pres), NOW).status == Status.PRESALE


def test_interpret_on_sale_and_sold_out():
    after = datetime(2026, 11, 20, tzinfo=timezone.utc)
    assert ticketmaster.interpret(tm_event("onsale"), after).status == Status.ON_SALE
    assert ticketmaster.interpret(tm_event("offsale"), after).status == Status.SOLD_OUT


def test_interpret_price_range():
    r = ticketmaster.interpret(tm_event(priceRanges=[{"min": 70.0, "max": 250.0, "currency": "EUR"}]), NOW)
    assert (r.price_min, r.price_max) == (70.0, 250.0)


def test_min_interval_respects_daily_quota():
    # 2 הופעות, מכסה 5000, שימוש ב-80% → לא פחות מ-44 שניות. לכן 10–30 שניות אינן מותרות כאן.
    assert ticketmaster.min_interval_seconds(2, 5000, 0.8) == 44
    assert ticketmaster.min_interval_seconds(1, 5000, 0.8) == 22


@pytest.mark.asyncio
@respx.mock
async def test_tm_search_not_found_means_not_announced():
    respx.get(f"{ticketmaster.BASE}/events.json").mock(return_value=httpx.Response(200, json={"page": {}}))
    async with httpx.AsyncClient() as c:
        r = await ticketmaster.check(c, {"keyword": "Stray Kids"}, EV, "K", NOW)
    assert r.status == Status.NOT_ANNOUNCED


@pytest.mark.asyncio
@respx.mock
async def test_tm_search_found_prefers_venue():
    other = tm_event() | {"id": "OTHER", "_embedded": {"venues": [{"name": "Other Arena"}]}}
    respx.get(f"{ticketmaster.BASE}/events.json").mock(
        return_value=httpx.Response(200, json={"_embedded": {"events": [other, tm_event()]}}))
    async with httpx.AsyncClient() as c:
        r = await ticketmaster.check(c, {"keyword": "Stray Kids", "venue_hint": "San Siro"}, EV, "K", NOW)
    assert r.external_id == "TMDEMO1"


@pytest.mark.asyncio
@respx.mock
async def test_tm_rate_limit_raises_with_retry_after():
    respx.get(f"{ticketmaster.BASE}/events.json").mock(return_value=httpx.Response(429, headers={"Retry-After": "120"}))
    async with httpx.AsyncClient() as c:
        with pytest.raises(SourceError) as ei:
            await ticketmaster.check(c, {}, EV, "K", NOW)
    assert ei.value.retry_after == 120


@pytest.mark.asyncio
async def test_tm_missing_key():
    async with httpx.AsyncClient() as c:
        with pytest.raises(SourceError):
            await ticketmaster.check(c, {}, EV, "", NOW)


def test_classify_rules():
    assert pagewatch.classify("General Onsale On sale soon")[0] == Status.ANNOUNCED
    assert pagewatch.classify("TICKETS HAVE NOW SOLD OUT")[0] == Status.SOLD_OUT
    assert pagewatch.classify("Buy tickets now")[0] == Status.ON_SALE
    assert pagewatch.classify("Nothing here")[0] == Status.ANNOUNCED


def test_combine_statuses():
    assert combine([Status.UNKNOWN, Status.UNKNOWN]) == Status.UNKNOWN
    assert combine([Status.SOLD_OUT, Status.ON_SALE]) == Status.ON_SALE
    assert combine([Status.NOT_ANNOUNCED, Status.ANNOUNCED]) == Status.ANNOUNCED


URL = "https://demo-site.invalid/event"


@pytest.fixture(autouse=True)
def _clear_robots():
    pagewatch._robots_cache.clear()


@pytest.mark.asyncio
@respx.mock
async def test_pagewatch_respects_robots():
    respx.get("https://demo-site.invalid/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /event"))
    async with httpx.AsyncClient() as c:
        with pytest.raises(SourceError) as ei:
            await pagewatch.check(c, {"url": URL}, None, "TestUA")
    assert ei.value.manual_action


@pytest.mark.asyncio
@respx.mock
async def test_pagewatch_blocked_requires_manual_action():
    respx.get("https://demo-site.invalid/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(URL).mock(return_value=httpx.Response(403, text="Access denied"))
    async with httpx.AsyncClient() as c:
        with pytest.raises(SourceError) as ei:
            await pagewatch.check(c, {"url": URL}, None, "TestUA")
    assert ei.value.manual_action and ei.value.http_status == 403


@pytest.mark.asyncio
@respx.mock
async def test_pagewatch_detects_change_and_status():
    respx.get("https://demo-site.invalid/robots.txt").mock(return_value=httpx.Response(404))
    route = respx.get(URL)
    route.mock(return_value=httpx.Response(200, text="<html><body><h1>On sale soon</h1></body></html>"))
    async with httpx.AsyncClient() as c:
        r1, h1 = await pagewatch.check(c, {"url": URL, "label": "דמה"}, None, "UA")
        route.mock(return_value=httpx.Response(200, text="<html><body><a>Buy tickets</a></body></html>"))
        r2, h2 = await pagewatch.check(c, {"url": URL, "label": "דמה"}, h1, "UA")
    assert r1.status == Status.ANNOUNCED and r2.status == Status.ON_SALE
    assert h1 != h2 and "השתנה" in r2.summary
