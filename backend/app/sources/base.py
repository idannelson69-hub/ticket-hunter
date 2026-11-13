from dataclasses import dataclass, field

from ..statuses import Status


class SourceError(Exception):
    """תקלה במקור. retry_after בשניות כשהאתר ביקש להמתין (429)."""

    def __init__(self, message: str, http_status: int | None = None, retry_after: int | None = None,
                 manual_action: bool = False):
        super().__init__(message)
        self.http_status = http_status
        self.retry_after = retry_after
        self.manual_action = manual_action  # למשל חסימת בוטים/CAPTCHA — לא עוקפים, מבקשים מהמשתמש


@dataclass
class SaleDate:
    name: str
    start_utc: str          # ISO, UTC
    verified: bool
    source: str


@dataclass
class CheckResult:
    status: Status
    summary: str
    http_status: int | None = None
    sale_dates: list[SaleDate] = field(default_factory=list)
    event_url: str | None = None
    external_id: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    offers: list[dict] = field(default_factory=list)   # נתוני הצעה בפורמט Offer
    is_demo: bool = False
