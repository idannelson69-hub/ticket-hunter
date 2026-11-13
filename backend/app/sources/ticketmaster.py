"""Ticketmaster Discovery API — ממשק רשמי ומורשה (מפתח חינמי ב-developer.ticketmaster.com).

מה ה-API נותן: קיום אירוע, קישור רשמי, סטטוס מכירה, מועדי מכירה מוקדמת וכללית, טווח מחירים.
מה הוא לא נותן: מלאי מושבים בזמן אמת (זה שמור לשותפים מסחריים בלבד).
"""
from datetime import datetime, timedelta, timezone

import httpx

from ..statuses import Status
from .base import CheckResult, SaleDate, SourceError

BASE = "https://app.ticketmaster.com/discovery/v2"


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def interpret(ev: dict, now: datetime) -> CheckResult:
    """ממיר אובייקט אירוע של Discovery API לסטטוס המערכת. פונקציה טהורה — נבדקת ביחידה."""
    code = (ev.get("dates", {}).get("status", {}) or {}).get("code", "")
    sales = ev.get("sales", {}) or {}
    public = sales.get("public", {}) or {}
    pub_start = _parse(public.get("startDateTime"))
    if public.get("startTBD") or public.get("startTBA"):
        pub_start = None

    sale_dates: list[SaleDate] = []
    presale_active = False
    for p in sales.get("presales", []) or []:
        s, e = _parse(p.get("startDateTime")), _parse(p.get("endDateTime"))
        if s:
            sale_dates.append(SaleDate(p.get("name", "מכירה מוקדמת"), s.astimezone(timezone.utc).isoformat(),
                                       True, "Ticketmaster API"))
        if s and s <= now and (e is None or now < e):
            presale_active = True
    if pub_start:
        sale_dates.append(SaleDate("מכירה כללית", pub_start.astimezone(timezone.utc).isoformat(),
                                   True, "Ticketmaster API"))

    if code in ("cancelled",):
        status, note = Status.UNKNOWN, "האירוע מסומן כמבוטל ב-Ticketmaster"
    elif code in ("postponed", "rescheduled"):
        status, note = Status.ANNOUNCED, f"האירוע מסומן {code} — בדוק תאריך"
    elif presale_active:
        status, note = Status.PRESALE, "מכירה מוקדמת פעילה"
    elif code == "onsale":
        if pub_start and pub_start > now:
            status, note = Status.ANNOUNCED, "מכירה כללית טרם נפתחה"
        else:
            status, note = Status.ON_SALE, "סטטוס onsale"
    elif code == "offsale":
        if pub_start is None or pub_start > now:
            status, note = Status.ANNOUNCED, "המכירה טרם נפתחה"
        else:
            status, note = Status.SOLD_OUT, "offsale אחרי פתיחת מכירה — כנראה אזל"
    else:
        status, note = Status.ANNOUNCED, f"סטטוס לא מוכר: {code or 'ריק'}"

    pr = (ev.get("priceRanges") or [{}])[0]
    venue = ((ev.get("_embedded") or {}).get("venues") or [{}])[0].get("name", "")
    return CheckResult(
        status=status,
        summary=f"Ticketmaster: {ev.get('name', '')} @ {venue} — {note}",
        sale_dates=sale_dates,
        event_url=ev.get("url"),
        external_id=ev.get("id"),
        price_min=pr.get("min"),
        price_max=pr.get("max"),
    )


async def check(client: httpx.AsyncClient, source: dict, event, api_key: str,
                now: datetime | None = None) -> CheckResult:
    if not api_key:
        raise SourceError("חסר TICKETMASTER_API_KEY — המקור מושבת עד להגדרה")
    now = now or datetime.now(timezone.utc)

    ext_id = source.get("external_id")
    if ext_id:
        r = await client.get(f"{BASE}/events/{ext_id}.json", params={"apikey": api_key})
        _raise_for(r)
        return interpret(r.json(), now)

    params = {"apikey": api_key, "keyword": source.get("keyword") or event.artist,
              "countryCode": source.get("country", "IT"), "size": 20, "sort": "date,asc"}
    if event.event_date:
        d = datetime(event.event_date.year, event.event_date.month, event.event_date.day, tzinfo=timezone.utc)
        params["startDateTime"] = (d - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params["endDateTime"] = (d + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = await client.get(f"{BASE}/events.json", params=params)
    _raise_for(r)
    events = ((r.json().get("_embedded") or {}).get("events")) or []
    venue_hint = (source.get("venue_hint") or "").lower()
    if venue_hint:
        matched = [e for e in events if venue_hint in str(e.get("_embedded", {}).get("venues", [{}])[0].get("name", "")).lower()]
        events = matched or events
    if not events:
        return CheckResult(status=Status.NOT_ANNOUNCED, summary="Ticketmaster: לא נמצא אירוע תואם", http_status=r.status_code)
    res = interpret(events[0], now)
    res.http_status = r.status_code
    return res


def _raise_for(r: httpx.Response):
    if r.status_code == 429:
        ra = r.headers.get("Retry-After")
        raise SourceError("Ticketmaster: חריגה ממגבלת קצב (429)", 429, int(ra) if ra and ra.isdigit() else 60)
    if r.status_code == 401:
        raise SourceError("Ticketmaster: מפתח API לא תקין (401)", 401)
    if r.status_code >= 400:
        raise SourceError(f"Ticketmaster: שגיאת HTTP {r.status_code}", r.status_code)


def min_interval_seconds(events_using_tm: int, quota: int, safety: float) -> int:
    """מרווח מינימלי בין בדיקות כך שלא נחרוג מהמכסה היומית של ה-API."""
    if events_using_tm <= 0:
        return 10
    allowed = max(1, int(quota * safety))
    return max(10, -(-86400 * events_using_tm // allowed))
