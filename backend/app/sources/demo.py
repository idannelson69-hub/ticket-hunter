"""מקור דמה — לסימולציה ולבדיקות בלבד. כל תוצאה מסומנת is_demo=True ומוצגת כ"דמה" בממשק ובטלגרם.

התרחיש מתקדם צעד אחד בכל בדיקה: טרם הוכרזה → הוכרזה → מכירה מוקדמת → מכירה + הצעות → אזל → חזרת מלאי.
"""
from datetime import datetime, timedelta, timezone

from ..statuses import Status
from .base import CheckResult, SaleDate

DEMO_OFFERS = [
    dict(source="דמה", section="DEMO-A1", row="5", seats="11-14", quantity=4, price_per_ticket=139.0,
         fees_included=True, seated=True, adjacent=True, view_score=4, restricted_view=False, location_score=4),
    dict(source="דמה", section="DEMO-B3", row="20", seats="1-4", quantity=4, price_per_ticket=99.0,
         fees_included=True, seated=True, adjacent=True, view_score=2, restricted_view=True, location_score=2),
    dict(source="דמה", section="DEMO-C2", row="8", seats="7-8", quantity=2, price_per_ticket=120.0,
         fees_included=True, seated=True, adjacent=True, view_score=4, restricted_view=False, location_score=3),
    dict(source="דמה", section="DEMO-C2", row="9", seats="7-8", quantity=2, price_per_ticket=125.0,
         fees_included=True, seated=True, adjacent=True, view_score=4, restricted_view=False, location_score=3),
    dict(source="דמה", section="DEMO-VIP", row="1", seats="1-4", quantity=4, price_per_ticket=290.0,
         fees_included=True, seated=True, adjacent=True, view_score=5, restricted_view=False, location_score=5),
]

DEMO_SALE_UTC = "2030-01-01T10:00:00+00:00"   # תאריך דמה קבוע ורחוק — לא קשור לשום מכירה אמיתית
SCENARIO = ["NOT_ANNOUNCED", "ANNOUNCED", "PRESALE", "AVAILABLE", "SOLD_OUT", "AVAILABLE"]


def check(step: int, now: datetime | None = None, scenario: list[str] | None = None) -> CheckResult:
    now = now or datetime.now(timezone.utc)
    sc = scenario or SCENARIO
    st = Status(sc[min(step, len(sc) - 1)])
    sale = []
    if st != Status.NOT_ANNOUNCED:
        sale = [SaleDate("[דמה] מכירה כללית", DEMO_SALE_UTC, True, "דמה")]
    offers = [dict(o) for o in DEMO_OFFERS] if st == Status.AVAILABLE else []
    return CheckResult(st, f"[דמה] צעד {step + 1}: {st.value}", 200, sale_dates=sale, offers=offers,
                       event_url="https://example.invalid/demo-event", is_demo=True)
