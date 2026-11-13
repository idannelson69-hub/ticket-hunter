"""מנוע סינון ודירוג הצעות. פונקציות טהורות — כל הכללים נבדקים בבדיקות יחידה.

עיקרון: מדרגים רק לפי מידע שקיים. שדה לא ידוע לא מקבל ציון "ממוצע" — הוא פשוט לא נספר,
והמשתמש רואה אזהרה שהמידע חסר.
"""
from dataclasses import dataclass
from itertools import combinations

WEIGHTS = {"price": 0.35, "adjacent": 0.25, "view": 0.30, "location": 0.10}
BASIS_HE = {"price": "מחיר", "adjacent": "סמיכות", "view": "ראות", "location": "מיקום"}


@dataclass
class Prefs:
    ticket_count: int
    max_price_per_ticket: float
    max_total: float
    seating: str = "any"
    require_adjacent: bool = True
    allow_split: bool = False
    allow_restricted_view: bool = False

    @classmethod
    def from_event(cls, ev) -> "Prefs":
        return cls(ev.ticket_count, ev.max_price_per_ticket, ev.max_total, ev.seating,
                   ev.require_adjacent, ev.allow_split, ev.allow_restricted_view)


def _get(o, k):
    return o.get(k) if isinstance(o, dict) else getattr(o, k, None)


def _as_dict(o) -> dict:
    keys = ["id", "source", "url", "section", "row", "seats", "quantity", "price_per_ticket", "fees_included",
            "seated", "adjacent", "view_score", "restricted_view", "location_score", "is_demo"]
    return {k: _get(o, k) for k in keys}


def score(o, prefs: Prefs) -> tuple[float, list[str]]:
    parts: dict[str, float] = {}
    price = _get(o, "price_per_ticket")
    if price is not None and prefs.max_price_per_ticket > 0:
        parts["price"] = max(0.0, min(1.0, (prefs.max_price_per_ticket - price) / prefs.max_price_per_ticket + 0.5))
    if _get(o, "adjacent") is not None:
        parts["adjacent"] = 1.0 if _get(o, "adjacent") else 0.0
    if _get(o, "view_score") is not None:
        parts["view"] = (max(1, min(5, _get(o, "view_score"))) - 1) / 4
    if _get(o, "location_score") is not None:
        parts["location"] = (max(1, min(5, _get(o, "location_score"))) - 1) / 4
    if not parts:
        return 0.0, []
    total_w = sum(WEIGHTS[k] for k in parts)
    s = sum(WEIGHTS[k] * v for k, v in parts.items()) / total_w
    return round(s * 100, 1), [BASIS_HE[k] for k in parts]


def _common_checks(o, prefs: Prefs, need: int, budget_cap: float) -> tuple[list[str], list[str], bool]:
    """מחזיר (סיבות פסילה, אזהרות, דורש_אישור)."""
    reasons, warnings, approval = [], [], False
    price = _get(o, "price_per_ticket")
    if price is None:
        reasons.append("אין מחיר")
        return reasons, warnings, approval
    if price > prefs.max_price_per_ticket:
        reasons.append(f"מחיר לכרטיס {price:.2f}€ מעל {prefs.max_price_per_ticket:.0f}€")
    if price * need > budget_cap + 1e-9:
        reasons.append(f"סה\"כ {price * need:.2f}€ מעל התקציב {budget_cap:.0f}€")
    fees = _get(o, "fees_included")
    if fees is False:
        warnings.append("המחיר לא כולל עמלות — הסכום בקופה יהיה גבוה יותר")
    elif fees is None:
        warnings.append("לא ידוע אם המחיר כולל עמלות")
    seated = _get(o, "seated")
    if prefs.seating == "seated":
        if seated is False:
            reasons.append("לא מקומות ישיבה")
        elif seated is None:
            warnings.append("לא ידוע אם אלה מקומות ישיבה")
    elif prefs.seating == "standing" and seated is True:
        reasons.append("מקומות ישיבה (נדרשה עמידה)")
    rv = _get(o, "restricted_view")
    if rv is True and not prefs.allow_restricted_view:
        approval = True
    elif rv is None:
        warnings.append("לא ידוע אם הראות מוגבלת")
    return reasons, warnings, approval


def evaluate(offers: list, prefs: Prefs, global_remaining: float | None = None) -> dict:
    budget_cap = prefs.max_total if global_remaining is None else min(prefs.max_total, global_remaining)
    need = prefs.ticket_count
    matches, needs_approval, excluded, split_pool = [], [], [], []

    for o in offers:
        d = _as_dict(o)
        qty = _get(o, "quantity") or 0
        reasons, warnings, approval = _common_checks(o, prefs, need, budget_cap)
        if qty < need:
            half = need // 2
            if prefs.allow_split and need >= 4 and qty >= half and _get(o, "adjacent") is not False:
                r2, w2, a2 = _common_checks(o, prefs, half, budget_cap)
                if not r2 and not a2:
                    split_pool.append(d | {"warnings": w2})
            reasons.append(f"רק {qty} כרטיסים (נדרשים {need})")
        if prefs.require_adjacent and _get(o, "adjacent") is False:
            reasons.append("המושבים לא צמודים")
        elif prefs.require_adjacent and _get(o, "adjacent") is None and qty >= need:
            warnings.append("לא ידוע אם המושבים צמודים")
        s, basis = score(o, prefs)
        price = _get(o, "price_per_ticket") or 0
        item = d | {"total": round(price * need, 2), "score": s, "basis": basis,
                    "warnings": warnings, "reasons": reasons}
        if reasons:
            excluded.append(item)
        elif approval:
            item["reasons"] = ["ראות מוגבלת — מוצג רק לאישורך"]
            needs_approval.append(item)
        else:
            matches.append(item)

    matches.sort(key=lambda x: (-x["score"], x["total"]))
    needs_approval.sort(key=lambda x: (-x["score"], x["total"]))

    split_options = []
    half = need // 2
    for a, b in combinations(split_pool, 2):
        total = round(a["price_per_ticket"] * half + b["price_per_ticket"] * half, 2)
        if total > budget_cap + 1e-9:
            continue
        sa, _ = score(a, prefs)
        sb, basis = score(b, prefs)
        split_options.append({"parts": [a, b], "total": total, "score": round((sa + sb) / 2, 1), "basis": basis,
                              "requires_approval": True,
                              "label": f"חלופת {half}+{half} — שתי קבוצות נפרדות, דורש אישור"})
    split_options.sort(key=lambda x: (-x["score"], x["total"]))
    if any(m.get("adjacent") for m in matches):
        split_options = []   # יש סט שלם צמוד — אין צורך בחלופה מפוצלת

    return {"matches": matches, "needs_approval": needs_approval, "split_options": split_options[:5],
            "excluded": excluded, "budget_cap": budget_cap}


def budget_summary(events: list, global_budget: float) -> dict:
    allocated = round(sum(e.max_total for e in events), 2)
    return {"global_budget": global_budget, "allocated": allocated,
            "ok": allocated <= global_budget + 1e-9, "remaining": round(global_budget - allocated, 2)}
