# 🎟️ צייד כרטיסים — מעקב מכירת כרטיסים להופעות

מערכת שעוקבת אחרי מכירת כרטיסים, שולחת התראות לטלפון בטלגרם, מדרגת הצעות לפי התקציב וההעדפות שלך,
ומדריכה אותך ברכישה. **המערכת אף פעם לא משלמת ולא עוקפת תור, CAPTCHA או אימות SMS.**

## מצב ההופעות (אומת ב-13.11.2026)

| | Stray Kids – Milano | Oasis – Roma |
|---|---|---|
| תאריך | שבת 31.7.2027 ✓ | 29.7.2027 ✓ (יש גם 26 ו-30 ביולי) |
| מקום | Stadio San Siro ✓ | Stadio Olimpico ✓ |
| מקור האימות | [Live Nation Italia — עמוד האירוע](https://www.livenation.it/en/event/stray-kids-world-tour-run-it-milan--milano-tickets-edp1711785) | [oasisinet.com/live](https://oasisinet.com/live/) |
| מכירה כללית | חמישי 19.11.2026 15:00 (שעון איטליה) = 16:00 שעון ישראל ✓ ב-Ticketmaster, TicketOne, Vivaticket | **אזל** ("TICKETS HAVE NOW SOLD OUT") |
| מכירות מוקדמות | 18.11.2026 — **דווח בתקשורת בלבד, לא אומת** | כרטיסי Resale רשמיים רק קרוב למועד, במחיר המקורי, דרך Ticketmaster ו-Twickets |
| מחירים / סוגי מושבים | טרם פורסמו בעמוד הרשמי | לא מוצגים כעובדה במערכת |

⚠️ **דחוף:** לפי דיווחים בתקשורת (לא מאומת), ההרשמה ל-Artist Presale של Stray Kids ב-LiveNation.com/StrayKids
נסגרת ביום ראשון 15.11.2026 בשעה 21:00 (שעון איטליה). כדאי לבדוק את זה עכשיו.

## מבנה הפרויקט

```
ticket-hunter/
├── backend/            שרת Python + FastAPI
│   ├── app/
│   │   ├── main.py         הפעלת השרת והגשת הממשק
│   │   ├── api.py          כל נקודות ה-API
│   │   ├── monitor.py      מנוע הניטור, תזכורות, בדיקת תקינות
│   │   ├── scheduler.py    מתזמן (דופק כל 5 שניות)
│   │   ├── ranking.py      מנוע סינון ודירוג הצעות
│   │   ├── notifier.py     Telegram + מניעת כפילויות
│   │   ├── purchase.py     תוכנית רכישה ידנית מודרכת
│   │   ├── seed.py         נתוני ההופעות המאומתים
│   │   └── sources/        Ticketmaster API, מעקב עמודים, מקור דמה
│   └── tests/          59 בדיקות אוטומטיות
├── frontend/           ממשק Next.js בעברית RTL
├── tools/purchase_helper.py   מסייע רכישה מקומי (Playwright)
├── deploy/Caddyfile    HTTPS אוטומטי
├── Dockerfile, docker-compose.yml, .env.example
└── docs/               מדריכים
```

## מדריכים
- [מדריך התקנה ופריסה לענן](docs/מדריך-התקנה.md)
- [מדריך הפעלה באנדרואיד](docs/מדריך-אנדרואיד.md)
- [מגבלות ותלויות חיצוניות](docs/מגבלות-ותלויות.md)

## הרצת הבדיקות
```bash
cd backend
../.venv/Scripts/python -m pytest -q
```
