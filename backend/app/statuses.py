from enum import Enum


class Status(str, Enum):
    NOT_ANNOUNCED = "NOT_ANNOUNCED"
    ANNOUNCED = "ANNOUNCED"
    PRESALE = "PRESALE"
    ON_SALE = "ON_SALE"
    AVAILABLE = "AVAILABLE"
    SOLD_OUT = "SOLD_OUT"
    UNKNOWN = "UNKNOWN"


STATUS_HE = {
    Status.NOT_ANNOUNCED: "טרם הוכרזה",
    Status.ANNOUNCED: "הוכרזה — המכירה טרם נפתחה",
    Status.PRESALE: "מכירה מוקדמת פתוחה",
    Status.ON_SALE: "מכירה כללית פתוחה",
    Status.AVAILABLE: "נמצאו כרטיסים זמינים",
    Status.SOLD_OUT: "אזל",
    Status.UNKNOWN: "לא ידוע",
}

# כאשר מקורות סותרים — הסטטוס "החזק" ביותר גובר (עדיף התראת-שווא מאשר החמצה)
PRIORITY = [
    Status.AVAILABLE,
    Status.ON_SALE,
    Status.PRESALE,
    Status.SOLD_OUT,
    Status.ANNOUNCED,
    Status.NOT_ANNOUNCED,
    Status.UNKNOWN,
]


def combine(statuses: list[Status]) -> Status:
    known = [s for s in statuses if s != Status.UNKNOWN]
    if not known:
        return Status.UNKNOWN
    return min(known, key=PRIORITY.index)
