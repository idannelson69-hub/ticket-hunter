"""נתוני פתיחה — רק עובדות שאומתו ב-13.11.2026 מול מקור רשמי, עם ציון המקור.
פרטים שנמצאו רק בתקשורת מסומנים verified=False ולא מקבלים ספירה לאחור או תזכורות.
"""
from datetime import date

from sqlalchemy.orm import Session

from .models import KV, Event

CHECKLIST = [
    {"id": "tm_account", "text": "חשבון Ticketmaster Italia פעיל", "done": False},
    {"id": "email", "text": "האימייל בחשבון אומת", "done": False},
    {"id": "login", "text": "בדקתי שאפשר להתחבר (כולל אימות דו-שלבי)", "done": False},
    {"id": "sms", "text": "בעיית SMS למספר ישראלי נבדקה מול התמיכה הרשמית", "done": False},
    {"id": "links", "text": "קישורי האירוע נבדקו ונפתחים", "done": False},
    {"id": "payment", "text": "אמצעי תשלום מוכן אצלי (לא נשמר במערכת)", "done": False},
    {"id": "telegram", "text": "התראת בדיקה בטלגרם התקבלה בטלפון", "done": False},
    {"id": "budget", "text": "התקציב הוגדר ואושר", "done": False},
    {"id": "skz_presale", "text": "Stray Kids: נרשמתי ל-Artist Presale ב-LiveNation.com/StrayKids (לפי דיווחים — עד 15.11.2026 21:00 שעון איטליה)", "done": False},
]

EVENTS = [
    dict(
        slug="stray-kids-milano-2027",
        artist="Stray Kids", city="Milano", venue="Stadio San Siro",
        event_date=date(2027, 7, 31), event_date_verified=True,
        verification_note=("אומת 13.11.2026 בעמוד הרשמי של Live Nation Italia: \"Stray Kids World Tour <RUN IT MILAN>\", "
                           "שבת 31.7.2027, Stadio San Siro. מכירה כללית: חמישי 19.11.2026 15:00 ב-Ticketmaster, TicketOne ו-Vivaticket. "
                           "מועדי Presale ב-18.11 דווחו בתקשורת בלבד ואינם מאומתים. סוגי מושבים ומחירים טרם פורסמו בעמוד הרשמי."),
        official_url="https://www.livenation.it/en/event/stray-kids-world-tour-run-it-milan--milano-tickets-edp1711785",
        ticket_count=4, max_price_per_ticket=150, max_total=600, seating="seated",
        require_adjacent=True, allow_split=True, allow_restricted_view=False,
        interval_seconds=300, status="ANNOUNCED",
        sources=[
            {"type": "ticketmaster_api", "label": "Ticketmaster API", "keyword": "Stray Kids", "country": "IT",
             "venue_hint": "San Siro", "enabled": True},
            {"type": "page_watch", "label": "Live Nation Italia",
             "url": "https://www.livenation.it/en/event/stray-kids-world-tour-run-it-milan--milano-tickets-edp1711785",
             "enabled": True},
        ],
        sale_dates=[
            {"name": "מכירה כללית", "start_utc": "2026-11-19T14:00:00+00:00", "verified": True,
             "source": "Live Nation Italia (עמוד רשמי)"},
            {"name": "STAY Membership Presale (דיווח תקשורתי)", "start_utc": "2026-11-18T10:00:00+00:00",
             "verified": False, "source": "תקשורת — לא מאומת"},
            {"name": "Artist Presale (דיווח תקשורתי)", "start_utc": "2026-11-18T14:00:00+00:00",
             "verified": False, "source": "תקשורת — לא מאומת"},
        ],
    ),
    dict(
        slug="oasis-roma-2027",
        artist="Oasis", city="Roma", venue="Stadio Olimpico",
        event_date=date(2027, 7, 29), event_date_verified=True,
        verification_note=("אומת 13.11.2026 באתר הרשמי oasisinet.com/live: \"29 Jul 2027 Rome, Italy / Stadio Olimpico\" "
                           "(וגם 26 ו-30 ביולי). בעמוד הבית הרשמי: \"TICKETS HAVE NOW SOLD OUT\"; כרטיסי Resale יהיו זמינים "
                           "רק קרוב למועד, במחיר המקורי, דרך Ticketmaster ו-Twickets. לא נמצא קישור אירוע ספציפי באתרים הרשמיים."),
        official_url="https://oasisinet.com/live/",
        ticket_count=2, max_price_per_ticket=150, max_total=300, seating="any",
        require_adjacent=True, allow_split=False, allow_restricted_view=False,
        interval_seconds=300, status="SOLD_OUT",
        sources=[
            {"type": "ticketmaster_api", "label": "Ticketmaster API", "keyword": "Oasis", "country": "IT",
             "venue_hint": "Olimpico", "enabled": True},
            {"type": "page_watch", "label": "oasisinet.com", "url": "https://oasisinet.com/", "enabled": True,
             "rules": [
                 {"pattern": r"resale (tickets )?(are )?(now )?(open|live|on sale|available now)", "status": "ON_SALE"},
                 {"pattern": r"sold\s*out", "status": "SOLD_OUT"},
                 {"pattern": r"buy tickets|get tickets", "status": "ON_SALE"},
             ]},
        ],
        sale_dates=[],
    ),
]

DEMO_EVENT = dict(
    slug="demo-event", artist="[דמה] אמן לדוגמה", city="עיר דמה", venue="אצטדיון דמה",
    event_date=date(2027, 8, 1), event_date_verified=False,
    verification_note="אירוע דמה לבדיקת המערכת בלבד. כל הנתונים מומצאים ומסומנים כדמה.",
    official_url="https://example.invalid/demo-event", ticket_count=4, max_price_per_ticket=150, max_total=600,
    seating="seated", require_adjacent=True, allow_split=True, interval_seconds=10, status="UNKNOWN",
    monitoring_enabled=False, sources=[{"type": "demo", "label": "מקור דמה", "enabled": True}], sale_dates=[],
)


def seed(db: Session, demo: bool = False) -> None:
    items = EVENTS + ([DEMO_EVENT] if demo else [])
    for data in items:
        if not db.query(Event).filter_by(slug=data["slug"]).first():
            db.add(Event(**data))
    if not db.get(KV, "global_budget"):
        db.add(KV(key="global_budget", value={"amount": 900, "currency": "EUR"}))
    if not db.get(KV, "checklist"):
        db.add(KV(key="checklist", value={"items": CHECKLIST}))
    db.commit()
