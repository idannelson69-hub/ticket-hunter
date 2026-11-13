import re
from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import auth, monitor, purchase, ranking
from .config import get_settings
from .db import get_db
from .models import KV, AuditLog, CheckRun, ErrorLog, Event, Notification, Offer
from .notifier import format_message
from .statuses import STATUS_HE, Status

public = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[Depends(auth.require_auth)])


def iso(dt):
    return monitor.aware(dt).isoformat() if dt else None


def audit(db: Session, action: str, detail: str = ""):
    db.add(AuditLog(action=action, detail=detail[:500]))
    db.commit()


def engine_of(request: Request):
    return request.app.state.engine


# ---------- ציבורי ----------
class LoginIn(BaseModel):
    password: str = Field(max_length=200)


@public.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    eng = engine_of(request)
    db.query(Event).count()
    return {"ok": True, "db": "ok", "scheduler_running": bool(eng and eng.running),
            "login_required": auth.login_required(request),
            "last_tick": iso(eng.last_tick) if eng else None, "time": datetime.now(timezone.utc).isoformat()}


@public.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth.login(request, response, body.password)
    audit(db, "login")
    return {"ok": True}


@public.post("/logout")
def logout(response: Response):
    auth.logout(response)
    return {"ok": True}


# ---------- הופעות ----------
def serialize_event(db: Session, ev: Event) -> dict:
    now = datetime.now(timezone.utc)
    future_verified = sorted(
        [d for d in ev.sale_dates or [] if d.get("verified") and datetime.fromisoformat(d["start_utc"]) > now],
        key=lambda d: d["start_utc"])
    srcs = []
    for i, s in enumerate(ev.sources or []):
        key = monitor.source_key(s, i)
        st = (ev.sources_state or {}).get(key, {})
        srcs.append({**{k: v for k, v in s.items() if k != "rules"}, "key": key,
                     "min_interval": monitor.source_min_interval(db, s),
                     "failures": st.get("failures", 0), "last_status": st.get("last_status"),
                     "next_allowed": st.get("next_allowed")})
    return {
        "id": ev.id, "slug": ev.slug, "artist": ev.artist, "city": ev.city, "venue": ev.venue,
        "event_date": ev.event_date.isoformat() if ev.event_date else None,
        "event_date_verified": ev.event_date_verified, "verification_note": ev.verification_note,
        "official_url": ev.official_url, "ticket_count": ev.ticket_count,
        "max_price_per_ticket": ev.max_price_per_ticket, "max_total": ev.max_total, "seating": ev.seating,
        "require_adjacent": ev.require_adjacent, "allow_split": ev.allow_split,
        "allow_restricted_view": ev.allow_restricted_view, "monitoring_enabled": ev.monitoring_enabled,
        "interval_seconds": ev.interval_seconds, "effective_interval": monitor.effective_interval(db, ev),
        "status": ev.status, "status_he": STATUS_HE[Status(ev.status)], "status_changed_at": iso(ev.status_changed_at),
        "sale_dates": ev.sale_dates or [], "next_verified_sale": future_verified[0] if future_verified else None,
        "last_check_at": iso(ev.last_check_at), "next_check_at": iso(ev.next_check_at) if ev.monitoring_enabled else None,
        "consecutive_failures": ev.consecutive_failures, "sources": srcs,
        "is_demo": any(s.get("type") == "demo" for s in ev.sources or []),
    }


@router.get("/events")
def list_events(db: Session = Depends(get_db)):
    return [serialize_event(db, e) for e in db.query(Event).order_by(Event.id).all()]


class SourceIn(BaseModel):
    type: str = Field(pattern="^(ticketmaster_api|page_watch|demo)$")
    label: str = Field(max_length=100)
    url: str | None = Field(default=None, max_length=500)
    keyword: str | None = Field(default=None, max_length=100)
    venue_hint: str | None = Field(default=None, max_length=100)
    country: str = "IT"
    enabled: bool = True


class EventIn(BaseModel):
    artist: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    venue: str = ""
    event_date: date | None = None
    event_date_verified: bool = False
    verification_note: str = ""
    official_url: str = ""
    ticket_count: int = Field(2, ge=1, le=10)
    max_price_per_ticket: float = Field(150, gt=0)
    max_total: float = Field(300, gt=0)
    seating: str = Field("any", pattern="^(seated|standing|any)$")
    require_adjacent: bool = True
    allow_split: bool = False
    allow_restricted_view: bool = False
    interval_seconds: int = Field(300, ge=10, le=86400)
    sources: list[SourceIn] = []


class EventPatch(BaseModel):
    ticket_count: int | None = Field(None, ge=1, le=10)
    max_price_per_ticket: float | None = Field(None, gt=0)
    max_total: float | None = Field(None, gt=0)
    seating: str | None = Field(None, pattern="^(seated|standing|any)$")
    require_adjacent: bool | None = None
    allow_split: bool | None = None
    allow_restricted_view: bool | None = None
    interval_seconds: int | None = Field(None, ge=10, le=86400)
    monitoring_enabled: bool | None = None
    official_url: str | None = None


def _validate_url(u: str | None):
    if u and not re.match(r"^https?://", u):
        raise HTTPException(422, "קישור חייב להתחיל ב-http:// או https://")


@router.post("/events")
def create_event(body: EventIn, db: Session = Depends(get_db)):
    _validate_url(body.official_url)
    for s in body.sources:
        _validate_url(s.url)
        if s.type == "page_watch" and not s.url:
            raise HTTPException(422, "מקור מסוג עמוד אינטרנט חייב קישור")
    base = re.sub(r"[^a-z0-9]+", "-", f"{body.artist}-{body.city}-{body.event_date or ''}".lower()).strip("-") or "event"
    slug, n = base, 1
    while db.query(Event).filter_by(slug=slug).first():
        n += 1
        slug = f"{base}-{n}"
    data = body.model_dump()
    data["sources"] = [s.model_dump(exclude_none=True) for s in body.sources]
    ev = Event(slug=slug, status="UNKNOWN", sale_dates=[], sources_state={}, **{k: v for k, v in data.items()})
    db.add(ev)
    db.commit()
    audit(db, "create_event", slug)
    return serialize_event(db, ev)


@router.patch("/events/{event_id}")
def patch_event(event_id: int, body: EventPatch, db: Session = Depends(get_db)):
    ev = _get_event(db, event_id)
    _validate_url(body.official_url)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ev, k, v)
    if body.monitoring_enabled:
        ev.next_check_at = None  # בדיקה מיידית בדופק הבא
    db.commit()
    audit(db, "update_event", f"{ev.slug}: {list(body.model_dump(exclude_none=True))}")
    return serialize_event(db, ev)


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    ev = _get_event(db, event_id)
    for model in (CheckRun, Offer):
        db.query(model).filter(model.event_id == ev.id).delete()
    db.delete(ev)
    db.commit()
    audit(db, "delete_event", ev.slug)
    return {"ok": True}


@router.post("/events/{event_id}/check")
async def check_now(event_id: int, request: Request, db: Session = Depends(get_db)):
    _get_event(db, event_id)
    return await engine_of(request).check_now(event_id)


@router.get("/events/{event_id}/history")
def history(event_id: int, limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(CheckRun).filter(CheckRun.event_id == event_id).order_by(CheckRun.id.desc()).limit(min(limit, 500))
    return [{"at": iso(r.started_at), "source": r.source_label, "ok": r.ok, "status": r.status,
             "http_status": r.http_status, "summary": r.summary, "is_demo": r.is_demo} for r in rows]


# ---------- הצעות ודירוג ----------
class OfferIn(BaseModel):
    source: str = Field("ידני", max_length=80)
    url: str = ""
    section: str = Field("", max_length=80)
    row: str = Field("", max_length=40)
    seats: str = Field("", max_length=120)
    quantity: int = Field(ge=1, le=20)
    price_per_ticket: float = Field(gt=0)
    fees_included: bool | None = None
    seated: bool | None = None
    adjacent: bool | None = None
    view_score: int | None = Field(None, ge=1, le=5)
    restricted_view: bool | None = None
    location_score: int | None = Field(None, ge=1, le=5)


@router.get("/events/{event_id}/offers")
def offers(event_id: int, db: Session = Depends(get_db)):
    ev = _get_event(db, event_id)
    active = db.query(Offer).filter(Offer.event_id == ev.id, Offer.active.is_(True)).all()
    return ranking.evaluate(active, ranking.Prefs.from_event(ev), monitor.global_remaining(db, ev))


@router.post("/events/{event_id}/offers")
def add_offer(event_id: int, body: OfferIn, db: Session = Depends(get_db)):
    ev = _get_event(db, event_id)
    _validate_url(body.url)
    db.add(Offer(event_id=ev.id, **body.model_dump()))
    db.commit()
    return offers(event_id, db)


@router.delete("/offers/{offer_id}")
def delete_offer(offer_id: int, db: Session = Depends(get_db)):
    o = db.get(Offer, offer_id)
    if o:
        db.delete(o)
        db.commit()
    return {"ok": True}


@router.get("/events/{event_id}/purchase-plan")
def purchase_plan(event_id: int, db: Session = Depends(get_db)):
    ev = _get_event(db, event_id)
    active = db.query(Offer).filter(Offer.event_id == ev.id, Offer.active.is_(True)).all()
    return purchase.build_plan(ev, active, monitor.global_remaining(db, ev))


# ---------- התראות, תקלות, הגדרות ----------
@router.get("/notifications")
def notifications(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(Notification).order_by(Notification.id.desc()).limit(min(limit, 500))
    return [{"id": n.id, "at": iso(n.created_at), "kind": n.kind, "event_id": n.event_id, "text": n.text,
             "sent": n.sent, "channels_sent": n.channels_sent or [], "error": n.error, "is_demo": n.is_demo}
            for n in rows]


@router.get("/errors")
def errors(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(ErrorLog).order_by(ErrorLog.id.desc()).limit(min(limit, 500))
    return [{"id": e.id, "at": iso(e.created_at), "event_id": e.event_id, "source": e.source_label,
             "level": e.level, "message": e.message} for e in rows]


@router.get("/settings")
def get_settings_api(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    channels = engine_of(request).notifier.channels()
    gb = db.get(KV, "global_budget")
    evs = [e for e in db.query(Event).filter(Event.monitoring_enabled.is_(True)).all() if not monitor.is_demo_event(e)]
    return {"global_budget": gb.value["amount"] if gb else None,
            "budget": ranking.budget_summary(evs, gb.value["amount"] if gb else 0),
            "telegram_configured": bool(s.telegram_bot_token and s.telegram_chat_id),
            "telegram_token_set": bool(s.telegram_bot_token),
            "channels": channels, "email_to": s.email_to,
            "ticketmaster_configured": bool(s.ticketmaster_api_key), "demo_mode": s.demo_mode,
            "min_page_watch_seconds": s.min_page_watch_seconds, "ticketmaster_daily_quota": s.ticketmaster_daily_quota}


class BudgetIn(BaseModel):
    global_budget: float = Field(gt=0, le=100000)


@router.put("/settings")
def put_settings(body: BudgetIn, request: Request, db: Session = Depends(get_db)):
    kv = db.get(KV, "global_budget") or KV(key="global_budget", value={})
    kv.value = {"amount": body.global_budget, "currency": "EUR"}
    db.merge(kv)
    db.commit()
    audit(db, "set_budget", str(body.global_budget))
    return get_settings_api(request, db)


class ChecklistIn(BaseModel):
    items: list[dict]


@router.get("/checklist")
def get_checklist(db: Session = Depends(get_db)):
    kv = db.get(KV, "checklist")
    return kv.value if kv else {"items": []}


@router.put("/checklist")
def put_checklist(body: ChecklistIn, db: Session = Depends(get_db)):
    items = [{"id": str(i.get("id"))[:40], "text": str(i.get("text"))[:300], "done": bool(i.get("done"))} for i in body.items]
    kv = KV(key="checklist", value={"items": items})
    db.merge(kv)
    db.commit()
    return {"items": items}


@router.post("/telegram/test")
async def telegram_test(request: Request, db: Session = Depends(get_db)):
    notifier = engine_of(request).notifier
    now = datetime.now(timezone.utc)
    text = format_message("test", None, details="אם קיבלת הודעה זו — ההתראות עובדות.", now=now)
    n = await notifier.notify(db, "test", f"test:{now.isoformat()}", text)
    return {"sent": n.sent, "channels_sent": n.channels_sent or [], "error": n.error}


@router.get("/telegram/discover")
async def telegram_discover():
    """עוזר למצוא את ה-chat_id: שלח הודעה כלשהי לבוט ואז קרא לכתובת זו."""
    tok = get_settings().telegram_bot_token
    if not tok:
        raise HTTPException(400, "TELEGRAM_BOT_TOKEN לא הוגדר")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"https://api.telegram.org/bot{tok}/getUpdates")
    if r.status_code != 200:
        raise HTTPException(502, "Telegram לא החזיר תשובה תקינה — בדוק את הטוקן")
    chats = {}
    for u in r.json().get("result", []):
        ch = (u.get("message") or {}).get("chat") or {}
        if ch.get("id"):
            chats[ch["id"]] = ch.get("first_name") or ch.get("title") or ""
    return {"chats": [{"chat_id": k, "name": v} for k, v in chats.items()]}


class PurgeIn(BaseModel):
    scope: str = Field(pattern="^(history|all)$")


@router.post("/data/purge")
def purge(body: PurgeIn, db: Session = Depends(get_db)):
    for model in (CheckRun, Notification, ErrorLog, Offer, AuditLog):
        db.query(model).delete()
    if body.scope == "all":
        db.query(Event).delete()
        db.query(KV).delete()
    db.commit()
    audit(db, "purge", body.scope)
    return {"ok": True, "scope": body.scope}


def _get_event(db: Session, event_id: int) -> Event:
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "הופעה לא נמצאה")
    return ev
