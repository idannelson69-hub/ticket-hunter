"""כניסה לממשק: סיסמה ממשתנה סביבה + עוגיית סשן חתומה (HttpOnly, SameSite=Strict)."""
import hmac
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings

COOKIE = "th_session"
MAX_AGE = 14 * 24 * 3600
_failed: dict[str, list[float]] = defaultdict(list)


def _serializer() -> URLSafeTimedSerializer:
    s = get_settings()
    if not s.session_secret or len(s.session_secret) < 16:
        raise HTTPException(503, "SESSION_SECRET לא הוגדר (לפחות 16 תווים) — הכניסה חסומה")
    return URLSafeTimedSerializer(s.session_secret, salt="th-session")


def login(request: Request, response: Response, password: str) -> None:
    s = get_settings()
    if not s.admin_password:
        raise HTTPException(503, "ADMIN_PASSWORD לא הוגדר — הכניסה חסומה")
    ip = request.client.host if request.client else "?"
    now = time.time()
    _failed[ip] = [t for t in _failed[ip] if now - t < 900]
    if len(_failed[ip]) >= 5:
        raise HTTPException(429, "יותר מדי ניסיונות כושלים. נסה שוב בעוד 15 דקות")
    if not hmac.compare_digest(password.encode(), s.admin_password.encode()):
        _failed[ip].append(now)
        raise HTTPException(401, "סיסמה שגויה")
    _failed.pop(ip, None)
    token = _serializer().dumps({"u": "admin"})
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, samesite="strict", secure=s.cookie_secure)


def logout(response: Response) -> None:
    response.delete_cookie(COOKIE)


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def login_required(request: Request) -> bool:
    """אפשר לוותר על סיסמה רק לגישה ישירה מהמחשב עצמו — לעולם לא לגישה מהאינטרנט."""
    if get_settings().require_login:
        return True
    host = request.client.host if request.client else ""
    return host not in LOCAL_HOSTS


def require_auth(request: Request) -> str:
    if not login_required(request):
        return "local"
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "נדרשת כניסה")
    try:
        data = _serializer().loads(token, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "הסשן פג — היכנס מחדש") from None
    return data.get("u", "")
