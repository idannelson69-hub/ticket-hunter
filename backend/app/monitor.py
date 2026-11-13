"""מנוע הניטור: מריץ בדיקה על כל מקורות ההופעה, מזהה שינויים ושולח התראות."""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from . import ranking
from .config import get_settings
from .models import CheckRun, ErrorLog, Event, KV, Offer
from .notifier import Notifier, format_message
from .sources import demo as demo_src
from .sources import pagewatch, ticketmaster
from .sources.base import CheckResult, SourceError
from .statuses import Status, combine

log = logging.getLogger("monitor")
REMINDER_TIERS = [("24 שעות", timedelta(hours=24)), ("שעה", timedelta(hours=1)), ("15 דקות", timedelta(minutes=15))]


def naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def source_key(src: dict, idx: int) -> str:
    return src.get("label") or f"{src.get('type')}-{idx}"


def source_min_interval(db: Session, src: dict) -> int:
    s = get_settings()
    t = src.get("type")
    if t == "ticketmaster_api":
        n = sum(1 for e in db.query(Event).filter(Event.monitoring_enabled.is_(True)).all()
                if any(x.get("type") == "ticketmaster_api" and x.get("enabled", True) for x in e.sources or []))
        return ticketmaster.min_interval_seconds(n, s.ticketmaster_daily_quota, s.ticketmaster_quota_safety)
    if t == "page_watch":
        return max(60, s.min_page_watch_seconds)
    if t == "demo":
        return 5
    return 300


def effective_interval(db: Session, ev: Event) -> int:
    srcs = [x for x in ev.sources or [] if x.get("enabled", True)]
    mins = [source_min_interval(db, x) for x in srcs] or [300]
    return max(ev.interval_seconds, min(mins))


def is_demo_event(ev: Event) -> bool:
    return any(s.get("type") == "demo" for s in ev.sources or [])


def global_remaining(db: Session, ev: Event) -> float | None:
    """כמה נשאר מהתקציב הכולל להופעה זו אחרי ההקצאות של שאר ההופעות האמיתיות. אירועי דמה לא נספרים."""
    kv = db.get(KV, "global_budget")
    if not kv or is_demo_event(ev):
        return None
    others = sum(e.max_total for e in db.query(Event).filter(Event.id != ev.id, Event.monitoring_enabled.is_(True))
                 if not is_demo_event(e))
    return kv.value.get("amount", 0) - others


def _offer_sig(o: dict) -> str:
    return "|".join(str(o.get(k, "")) for k in ("source", "section", "row", "seats", "price_per_ticket", "quantity"))


async def run_check(db: Session, ev: Event, client: httpx.AsyncClient, notifier: Notifier,
                    now: datetime | None = None, tolerance_seconds: int = 0) -> dict:
    """tolerance_seconds: במצב הרצה מתוזמנת (GitHub) ההרצה עשויה להגיע כמה שניות 'מוקדם' — לא מדלגים עליה."""
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    state = {k: dict(v) for k, v in (ev.sources_state or {}).items()}
    sources = [dict(x) for x in ev.sources or []]
    results: list[tuple[str, CheckResult]] = []
    attempted = 0

    for idx, src in enumerate(sources):
        if not src.get("enabled", True):
            continue
        key = source_key(src, idx)
        st = state.get(key, {})
        na = st.get("next_allowed")
        if na and now + timedelta(seconds=tolerance_seconds) < datetime.fromisoformat(na):
            continue  # המקור בהמתנה (מגבלת קצב / backoff)
        attempted += 1
        try:
            t = src.get("type")
            if t == "ticketmaster_api":
                res = await ticketmaster.check(client, src, ev, s.ticketmaster_api_key, now)
                if res.external_id and not src.get("external_id"):
                    src["external_id"] = res.external_id
                    src["event_url"] = res.event_url
            elif t == "page_watch":
                res, digest = await pagewatch.check(client, src, st.get("hash"), s.user_agent)
                st["hash"] = digest
            elif t == "demo":
                step = int(st.get("step", 0))
                res = demo_src.check(step, now, src.get("scenario"))
                st["step"] = step + 1
            else:
                raise SourceError(f"סוג מקור לא מוכר: {t}")
            st["failures"] = 0
            st["last_status"] = res.status.value
            st["next_allowed"] = (now + timedelta(seconds=max(ev.interval_seconds,
                                                              source_min_interval(db, src)) - 1)).isoformat()
            results.append((key, res))
            db.add(CheckRun(event_id=ev.id, source_label=key, started_at=naive(now), ok=True,
                            status=res.status.value, http_status=res.http_status, summary=res.summary[:1000],
                            is_demo=res.is_demo))
        except (SourceError, httpx.HTTPError, ValueError) as e:
            fails = int(st.get("failures", 0)) + 1
            st["failures"] = fails
            retry_after = getattr(e, "retry_after", None)
            base = max(ev.interval_seconds, source_min_interval(db, src))
            backoff = retry_after or min(base * (2 ** min(fails, 10)), s.max_backoff_seconds)
            st["next_allowed"] = (now + timedelta(seconds=backoff)).isoformat()
            msg = str(e) or e.__class__.__name__
            db.add(CheckRun(event_id=ev.id, source_label=key, started_at=naive(now), ok=False, status="UNKNOWN",
                            http_status=getattr(e, "http_status", None), summary=msg[:1000]))
            db.add(ErrorLog(event_id=ev.id, source_label=key, level="warning", message=f"{msg} · המתנה {backoff} שנ'"))
            if getattr(e, "manual_action", False):
                await notifier.notify(db, "manual", f"manual:{ev.id}:{key}:{now:%Y%m%d}",
                                      format_message("manual", ev, site=key, details=msg, now=now), ev.id)
        state[key] = st

    ev.sources = sources
    ev.sources_state = state
    ev.last_check_at = naive(now)
    ev.next_check_at = naive(now + timedelta(seconds=effective_interval(db, ev)))
    events_out: list[str] = []

    if attempted and not results:
        ev.consecutive_failures += 1
        if ev.consecutive_failures >= s.critical_after_failures:
            await notifier.notify(db, "critical", f"critical:{ev.id}:{now:%Y%m%d%H}",
                                  format_message("critical", ev, details=f"{ev.consecutive_failures} בדיקות רצופות נכשלו",
                                                 now=now), ev.id)
            events_out.append("critical")
    elif results:
        ev.consecutive_failures = 0

    is_demo = any(r.is_demo for _, r in results)

    # --- מועדי מכירה: זיהוי חדשים/שינויים ---
    old_dates = list(ev.sale_dates or [])
    result_sources = {sd.source for _, r in results for sd in r.sale_dates}
    new_dates = [d for d in old_dates if d.get("source") not in result_sources]
    for _, r in results:
        for sd in r.sale_dates:
            entry = {"name": sd.name, "start_utc": sd.start_utc, "verified": sd.verified, "source": sd.source}
            new_dates.append(entry)
            if not any(d.get("name") == sd.name and d.get("start_utc") == sd.start_utc for d in old_dates):
                details = f"{sd.name}: {_fmt_iso(sd.start_utc)} (שעון ישראל) · מקור: {sd.source}"
                n = await notifier.notify(db, "sale_date", f"sale:{ev.id}:{sd.name}:{sd.start_utc}",
                                          format_message("sale_date", ev, site=sd.source, details=details,
                                                         is_demo=r.is_demo, now=now), ev.id, r.is_demo)
                if n:
                    events_out.append("sale_date")
    ev.sale_dates = new_dates

    # --- הצעות ---
    # רק מקורות שמחזירים רשימת הצעות מלאה (כיום: דמה) מעדכנים את טבלת ההצעות. הצעות ידניות לא נגעות.
    for key, r in results:
        if not r.is_demo:
            continue
        sigs = {_offer_sig(o) for o in r.offers}
        current = db.query(Offer).filter(Offer.event_id == ev.id, Offer.is_demo.is_(True), Offer.active.is_(True)).all()
        for old in current:
            if _offer_sig(old.__dict__) not in sigs:
                old.active = False
        existing = {_offer_sig(o.__dict__) for o in current if o.active}
        for o in r.offers:
            if _offer_sig(o) not in existing:
                db.add(Offer(event_id=ev.id, url=r.event_url or "", is_demo=True, **o))
    db.flush()

    # --- סטטוס ---
    if results:
        new_status = combine([r.status for _, r in results])
        old_status = Status(ev.status)
        if new_status != Status.UNKNOWN and new_status != old_status:
            tcount = int(state.get("_meta", {}).get("transitions", 0)) + 1
            state.setdefault("_meta", {})["transitions"] = tcount
            ev.sources_state = state
            kind = _transition_kind(old_status, new_status)
            ev.status = new_status.value
            ev.status_changed_at = naive(now)
            if kind:
                link = next((r.event_url for _, r in results if r.event_url), "") or ev.official_url
                price = next((f"{r.price_min:.0f}–{r.price_max:.0f}€ (טווח רשמי)" for _, r in results
                              if r.price_min is not None and r.price_max is not None), "")
                await notifier.notify(db, kind, f"status:{ev.id}:{tcount}:{new_status.value}",
                                      format_message(kind, ev, site=", ".join(k for k, _ in results), price=price,
                                                     link=link, is_demo=is_demo, now=now), ev.id, is_demo)
                events_out.append(kind)

    # --- התאמות ---
    active = db.query(Offer).filter(Offer.event_id == ev.id, Offer.active.is_(True)).all()
    if active:
        ev_res = ranking.evaluate(active, ranking.Prefs.from_event(ev), global_remaining(db, ev))
        for m in ev_res["matches"][:3]:
            details = (f"גוש {m['section']} שורה {m['row']} מושבים {m['seats']} · ציון {m['score']} "
                       f"(לפי {', '.join(m['basis']) or '—'})")
            if m["warnings"]:
                details += "\n⚠️ " + " | ".join(m["warnings"])
            details += "\nהמערכת לא מבצעת תשלום — נדרש אישורך ורכישה ידנית."
            n = await notifier.notify(db, "match", f"match:{ev.id}:{_offer_sig(m)}",
                                      format_message("match", ev, site=m["source"],
                                                     price=f"{m['price_per_ticket']:.2f}€ לכרטיס · סה\"כ {m['total']:.2f}€",
                                                     link=m["url"] or ev.official_url, details=details,
                                                     is_demo=bool(m["is_demo"]), now=now), ev.id, bool(m["is_demo"]))
            if n:
                events_out.append("match")
        for sp in ev_res["split_options"][:1]:
            a, b = sp["parts"]
            details = f"{sp['label']}: {a['section']}/{a['row']} + {b['section']}/{b['row']}"
            await notifier.notify(db, "match", f"split:{ev.id}:{_offer_sig(a)}+{_offer_sig(b)}",
                                  format_message("match", ev, site=a["source"], price=f"סה\"כ {sp['total']:.2f}€",
                                                 details=details, is_demo=bool(a["is_demo"]), now=now),
                                  ev.id, bool(a["is_demo"]))

    db.commit()
    return {"event_id": ev.id, "status": ev.status, "results": len(results), "attempted": attempted,
            "notifications": events_out}


def _transition_kind(old: Status, new: Status) -> str | None:
    if new == Status.ANNOUNCED and old in (Status.NOT_ANNOUNCED, Status.UNKNOWN):
        return "announced" if old == Status.NOT_ANNOUNCED else None
    if new == Status.PRESALE:
        return "presale"
    if new in (Status.ON_SALE, Status.AVAILABLE):
        return "restock" if old == Status.SOLD_OUT else ("on_sale" if old not in (Status.ON_SALE, Status.AVAILABLE) else None)
    if new == Status.SOLD_OUT:
        return "sold_out"
    return None


def _fmt_iso(iso: str) -> str:
    from .notifier import fmt_local
    return fmt_local(datetime.fromisoformat(iso))


async def send_reminders(db: Session, notifier: Notifier, now: datetime | None = None) -> int:
    """תזכורות 24 שעות / שעה / 15 דקות — רק למועדים מאומתים. כל שכבה נשלחת רק בחלון שלה."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    for ev in db.query(Event).filter(Event.monitoring_enabled.is_(True)).all():
        for sd in ev.sale_dates or []:
            if not sd.get("verified"):
                continue
            start = aware(datetime.fromisoformat(sd["start_utc"]))
            if not start or now >= start:
                continue
            for i, (label, off) in enumerate(REMINDER_TIERS):
                upper = start - REMINDER_TIERS[i + 1][1] if i + 1 < len(REMINDER_TIERS) else start
                if start - off <= now < upper:
                    is_demo = sd.get("source") == "דמה"
                    details = f"בעוד {label}: {sd['name']} · {_fmt_iso(sd['start_utc'])} (שעון ישראל)\nבדוק את רשימת ההכנה בממשק."
                    n = await notifier.notify(db, "reminder", f"rem:{ev.id}:{sd['name']}:{sd['start_utc']}:{i}",
                                              format_message("reminder", ev, site=sd.get("source", ""), details=details,
                                                             is_demo=is_demo, now=now), ev.id, is_demo)
                    sent += 1 if n else 0
    return sent


async def health_check(db: Session, notifier: Notifier, now: datetime | None = None) -> list[str]:
    """מזהה הופעות שהניטור שלהן 'נתקע' ושולח התראה קריטית (פעם בשעה לכל היותר)."""
    now = now or datetime.now(timezone.utc)
    stale = []
    for ev in db.query(Event).filter(Event.monitoring_enabled.is_(True)).all():
        limit = max(3 * effective_interval(db, ev), 900)
        last = aware(ev.last_check_at)
        if last and (now - last).total_seconds() > limit:
            stale.append(ev.slug)
            await notifier.notify(db, "critical", f"stale:{ev.id}:{now:%Y%m%d%H}",
                                  format_message("critical", ev, details="הניטור לא רץ כמתוכנן — בדוק את השרת", now=now),
                                  ev.id)
    await notifier.retry_unsent(db)
    return stale
