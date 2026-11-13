"""מסייע רכישה — מצב 'רכישה ידנית מודרכת'.

למה לא אוטומציה מלאה של סל וקופה: תנאי השימוש של Ticketmaster ושל רוב אתרי הכרטיסים אוסרים שימוש
בבוטים/סקריפטים לרכישה, והאתרים מגינים על עצמם בתור וירטואלי ו-CAPTCHA שאסור לעקוף.
לכן המערכת מכינה הכול מראש (קישור ישיר, כמות, תקציב, ההצעה המדורגת), ואתה מבצע את הלחיצות.
כלי עזר מקומי (tools/purchase_helper.py) פותח את העמוד בדפדפן אמיתי שלך ומציג את ההעדפות — בלי ללחוץ במקומך.
"""
from . import ranking
from .models import Event

AUTOMATION_POLICY = {
    "Ticketmaster": "אוסר רכישה אוטומטית בתנאי השימוש → רכישה ידנית מודרכת",
    "TicketOne": "אין ממשק רשמי לרכישה; אוטומציה אסורה → רכישה ידנית מודרכת",
    "Vivaticket": "אין ממשק רשמי לרכישה → רכישה ידנית מודרכת",
    "Twickets": "מכירה חוזרת רשמית (Oasis) — רכישה ידנית בלבד",
}


def build_plan(ev: Event, offers: list, global_remaining: float | None) -> dict:
    prefs = ranking.Prefs.from_event(ev)
    evaluation = ranking.evaluate(offers, prefs, global_remaining)
    best = evaluation["matches"][0] if evaluation["matches"] else None
    links = [{"label": "עמוד רשמי", "url": ev.official_url}] if ev.official_url else []
    for s in ev.sources or []:
        u = s.get("event_url") or (s.get("url") if s.get("type") == "page_watch" else None)
        if u and all(u != l["url"] for l in links):
            links.append({"label": s.get("label", "מקור"), "url": u})
    seat_txt = "ישיבה בלבד" if ev.seating == "seated" else ("עמידה" if ev.seating == "standing" else "לפי ההגדרה")
    steps = [
        "פתח את הקישור הרשמי מהמחשב או מהטלפון — עדיף לפני מועד הפתיחה ולהיות מחובר לחשבון.",
        "אם מופיע תור וירטואלי — להמתין בו. לא לרענן ולא לפתוח עשרות לשוניות.",
        f"בחר {ev.ticket_count} כרטיסים · {seat_txt}" + (" · מושבים צמודים" if ev.require_adjacent else ""),
        f"סנן מחיר: עד {ev.max_price_per_ticket:.0f}€ לכרטיס כולל עמלות, ועד {ev.max_total:.0f}€ סה\"כ.",
    ]
    if best:
        steps.append(f"ההצעה המובילה במערכת: גוש {best['section']} שורה {best['row']} · {best['price_per_ticket']:.2f}€ לכרטיס"
                     + (" [דמה]" if best.get("is_demo") else ""))
    if ev.allow_split and ev.ticket_count >= 4:
        steps.append("אם אין 4 צמודים — אפשר לשקול 2+2 (המערכת תציע, אתה מאשר).")
    steps += [
        "הוסף לסל והתקדם לקופה. בדוק את המחיר הכולל (כולל עמלות) מול התקציב.",
        "⛔ עצור לפני תשלום: אשר רק אם המחיר הכולל, הכמות והמושבים תואמים. התשלום והאימות (SMS/בנק) — אצלך בלבד.",
    ]
    return {"mode": "manual_guided", "links": links, "steps": steps, "best": best,
            "split_options": evaluation["split_options"], "needs_approval": evaluation["needs_approval"],
            "policy": AUTOMATION_POLICY, "budget_cap": evaluation["budget_cap"]}
