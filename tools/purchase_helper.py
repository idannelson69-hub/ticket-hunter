"""מסייע רכישה מקומי — רץ על המחשב שלך (לא בענן), עם Playwright.

מה הוא עושה:
  * פותח דפדפן Chromium אמיתי וגלוי, עם פרופיל קבוע (browser-profile/) — כך ההתחברות שלך לאתר נשמרת בין הפעלות.
  * מנווט לעמוד האירוע הרשמי ומציג בטרמינל את ההעדפות: כמות, תקציב, סוג מושב, ההצעה המובילה מהמערכת.
  * לא לוחץ, לא ממלא טפסים, לא עוקף תור/CAPTCHA/SMS ולא משלם. אתה מבצע את הרכישה בעצמך.

למה לא אוטומציה מלאה: תנאי השימוש של Ticketmaster ושל אתרי הכרטיסים האחרים אוסרים רכישה באמצעות בוטים/סקריפטים.

התקנה (פעם אחת):
    pip install playwright
    python -m playwright install chromium
הפעלה:
    python tools/purchase_helper.py --url "https://www.livenation.it/en/event/..." --tickets 4 --max-price 150 --max-total 600 --seated
"""
import argparse
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="מסייע רכישה ידנית מודרכת")
    p.add_argument("--url", required=True, help="קישור לעמוד האירוע הרשמי")
    p.add_argument("--tickets", type=int, required=True)
    p.add_argument("--max-price", type=float, required=True, help="מקסימום לכרטיס כולל עמלות (€)")
    p.add_argument("--max-total", type=float, required=True, help="תקציב כולל (€)")
    p.add_argument("--seated", action="store_true", help="ישיבה בלבד")
    p.add_argument("--best", default="", help="תיאור ההצעה המובילה מהממשק (לא חובה)")
    a = p.parse_args()

    if not a.url.startswith("https://"):
        print("הקישור חייב להתחיל ב-https://")
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("חסר Playwright. הרץ: pip install playwright && python -m playwright install chromium")
        return 2

    profile = Path(__file__).resolve().parent.parent / "browser-profile"
    profile.mkdir(exist_ok=True)
    print("\n================ העדפות רכישה ================")
    print(f"כמות: {a.tickets} כרטיסים{' · ישיבה בלבד · צמודים' if a.seated else ''}")
    print(f"עד {a.max_price:.0f}€ לכרטיס כולל עמלות · עד {a.max_total:.0f}€ סה\"כ")
    if a.best:
        print(f"ההצעה המובילה במערכת: {a.best}")
    print("-----------------------------------------------")
    print("1. התחבר לחשבון באתר (פעם ראשונה בלבד — נשמר בפרופיל).")
    print("2. אם יש תור וירטואלי — המתן בו. אל תרענן.")
    print("3. בחר כמות וסנן מחיר. הוסף לסל והתקדם לקופה.")
    print("4. ⛔ לפני תשלום: ודא שהסכום הכולל ≤ התקציב, הכמות והמושבים נכונים. התשלום והאימות — רק אתה.")
    print("סגור את חלון הדפדפן כדי לסיים.\n")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(profile), headless=False, locale="it-IT",
                                                    viewport=None, args=["--start-maximized"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(a.url, wait_until="domcontentloaded")
        try:
            ctx.wait_for_event("close", timeout=0)
        except Exception:  # noqa: BLE001 — המשתמש סגר את החלון
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
