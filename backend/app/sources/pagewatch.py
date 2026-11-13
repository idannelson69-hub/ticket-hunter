"""מעקב אחרי עמוד אינטרנט רשמי בתדירות נמוכה.

עקרונות: מכבדים robots.txt, לא יותר מפעם ב-5 דקות (ברירת מחדל), מזדהים ב-User-Agent,
ואם האתר מציג חסימת בוטים / CAPTCHA / תור וירטואלי — עוצרים ומבקשים פעולה ידנית. לא עוקפים.
"""
import hashlib
import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from ..statuses import Status
from .base import CheckResult, SourceError

DEFAULT_RULES = [
    {"pattern": r"on sale soon|coming soon|in arrivo|prossimamente|disponibili a breve", "status": "ANNOUNCED"},
    {"pattern": r"sold\s*out|esaurito|tutto esaurito", "status": "SOLD_OUT"},
    {"pattern": r"buy tickets|get tickets|find tickets|acquista|compra biglietti", "status": "ON_SALE"},
    {"pattern": r"presale|prevendita", "status": "PRESALE"},
]
BLOCK_MARKERS = re.compile(r"captcha|queue-it|cf-chl|are you a robot|access denied|verify you are human", re.I)

_robots_cache: dict[str, RobotFileParser | None] = {}


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def classify(text: str, rules: list[dict] | None = None) -> tuple[Status, str]:
    for rule in rules or DEFAULT_RULES:
        m = re.search(rule["pattern"], text, re.I)
        if m:
            return Status(rule["status"]), m.group(0)
    return Status.ANNOUNCED, ""   # העמוד הרשמי קיים ואין סימן אחר


async def robots_allows(client: httpx.AsyncClient, url: str, ua: str) -> bool:
    p = urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    if root not in _robots_cache:
        try:
            r = await client.get(root + "/robots.txt", timeout=10)
            if r.status_code == 200:
                rp = RobotFileParser()
                rp.parse(r.text.splitlines())
                _robots_cache[root] = rp
            else:
                _robots_cache[root] = None
        except httpx.HTTPError:
            _robots_cache[root] = None
    rp = _robots_cache[root]
    return True if rp is None else rp.can_fetch(ua, url)


async def check(client: httpx.AsyncClient, source: dict, prev_hash: str | None, ua: str) -> tuple[CheckResult, str]:
    url = source["url"]
    if not await robots_allows(client, url, ua):
        raise SourceError(f"robots.txt של {urlparse(url).netloc} אוסר בדיקה אוטומטית של העמוד — עבור לבדיקה ידנית",
                          manual_action=True)
    r = await client.get(url, headers={"User-Agent": ua, "Accept-Language": "it,en;q=0.8"},
                         follow_redirects=True, timeout=20)
    if r.status_code == 429:
        ra = r.headers.get("Retry-After")
        raise SourceError("האתר ביקש להאט (429)", 429, int(ra) if ra and ra.isdigit() else 600)
    if r.status_code in (401, 403) or BLOCK_MARKERS.search(r.text[:20000] if r.status_code != 200 else ""):
        raise SourceError(f"האתר חוסם בדיקה אוטומטית (HTTP {r.status_code}) — לא עוקפים, נדרשת בדיקה ידנית",
                          r.status_code, manual_action=True)
    if r.status_code == 404:
        return CheckResult(Status.NOT_ANNOUNCED, "העמוד לא נמצא (404)", 404), prev_hash or ""
    if r.status_code >= 400:
        raise SourceError(f"שגיאת HTTP {r.status_code}", r.status_code)

    text = strip_html(r.text)
    if BLOCK_MARKERS.search(text[:3000]) and len(text) < 3000:
        raise SourceError("זוהה עמוד אימות/תור — לא עוקפים, נדרשת פעולה ידנית", r.status_code, manual_action=True)
    digest = hashlib.sha256(text.encode()).hexdigest()
    status, hit = classify(text, source.get("rules"))
    changed = prev_hash is not None and prev_hash != digest
    found = f"נמצא «{hit}»" if hit else "אין סימן מכירה"
    summary = f"{source.get('label', url)}: {found}" + (" · התוכן השתנה" if changed else "")
    return CheckResult(status, summary, r.status_code, event_url=url), digest
