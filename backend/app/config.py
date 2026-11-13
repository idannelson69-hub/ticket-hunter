"""הגדרות המערכת — נקראות ממשתני סביבה בלבד (אין סודות בקוד)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # בסיס נתונים
    database_url: str = "sqlite:///./data/tickets.db"

    # כניסה לממשק
    admin_password: str = ""          # חובה בפריסה. ריק = כניסה חסומה
    session_secret: str = ""          # מחרוזת אקראית ארוכה
    cookie_secure: bool = False       # true מאחורי HTTPS
    # false = בלי סיסמה, אבל רק לגישה מהמחשב עצמו (localhost). גישה מבחוץ עדיין דורשת סיסמה.
    require_login: bool = True

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # מייל (SMTP). ל-Gmail: smtp.gmail.com, פורט 587, ו"סיסמת אפליקציה" (לא הסיסמה הרגילה)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""                # אפשר כמה כתובות מופרדות בפסיק

    # Ticketmaster Discovery API (רשמי, חינמי — developer.ticketmaster.com)
    ticketmaster_api_key: str = ""
    ticketmaster_daily_quota: int = 5000      # המכסה הרשמית לחשבון חינמי
    ticketmaster_quota_safety: float = 0.8    # משתמשים רק ב-80% מהמכסה

    # ניטור
    min_page_watch_seconds: int = 300         # עמודי אינטרנט — לא יותר מפעם ב-5 דקות
    critical_after_failures: int = 5          # התראה קריטית אחרי X כשלונות רצופים
    max_backoff_seconds: int = 3600
    user_agent: str = "TicketHunter/1.0 (personal fan alert tool; low-frequency)"

    # מצב הדגמה — מקור דמה מסומן בבירור
    demo_mode: bool = False

    timezone_display: str = "Asia/Jerusalem"
    scheduler_enabled: bool = True
    static_dir: str = "../frontend/out"


@lru_cache
def get_settings() -> Settings:
    return Settings()
