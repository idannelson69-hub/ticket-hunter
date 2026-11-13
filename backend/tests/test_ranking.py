"""בדיקות מנוע הסינון והדירוג + תקציב כולל. כל ההצעות כאן הן נתוני דמה."""
from types import SimpleNamespace

from app.ranking import Prefs, budget_summary, evaluate, score

SKZ = Prefs(ticket_count=4, max_price_per_ticket=150, max_total=600, seating="seated",
            require_adjacent=True, allow_split=True, allow_restricted_view=False)
OASIS = Prefs(ticket_count=2, max_price_per_ticket=150, max_total=300, seating="any",
              require_adjacent=True, allow_split=False)


def offer(**kw):
    base = dict(id=None, source="דמה", url="", section="A", row="1", seats="1-4", quantity=4, price_per_ticket=120.0,
                fees_included=True, seated=True, adjacent=True, view_score=4, restricted_view=False,
                location_score=3, is_demo=True)
    return base | kw


def test_valid_offer_matches():
    r = evaluate([offer()], SKZ)
    assert len(r["matches"]) == 1
    assert r["matches"][0]["total"] == 480.0


def test_price_per_ticket_over_limit_excluded():
    r = evaluate([offer(price_per_ticket=150.01)], SKZ)
    assert not r["matches"] and r["excluded"]
    assert "מעל 150" in r["excluded"][0]["reasons"][0]


def test_exact_limit_allowed():
    assert evaluate([offer(price_per_ticket=150.0)], SKZ)["matches"]


def test_total_budget_enforced_by_global_remaining():
    # 4×140=560 בתוך 600, אבל אם נשארו רק 500 מהתקציב הכולל — נפסל
    assert evaluate([offer(price_per_ticket=140)], SKZ)["matches"]
    r = evaluate([offer(price_per_ticket=140)], SKZ, global_remaining=500)
    assert not r["matches"] and r["budget_cap"] == 500


def test_standing_excluded_for_seated_event():
    r = evaluate([offer(seated=False)], SKZ)
    assert not r["matches"] and "ישיבה" in r["excluded"][0]["reasons"][0]


def test_unknown_seating_kept_with_warning():
    r = evaluate([offer(seated=None)], SKZ)
    assert r["matches"] and any("ישיבה" in w for w in r["matches"][0]["warnings"])


def test_restricted_view_needs_approval():
    r = evaluate([offer(restricted_view=True)], SKZ)
    assert not r["matches"] and len(r["needs_approval"]) == 1


def test_restricted_view_allowed_when_user_approved():
    p = Prefs(**{**SKZ.__dict__, "allow_restricted_view": True})
    assert evaluate([offer(restricted_view=True)], p)["matches"]


def test_non_adjacent_excluded():
    r = evaluate([offer(adjacent=False)], SKZ)
    assert not r["matches"]


def test_split_2_plus_2_offered_when_no_four_adjacent():
    r = evaluate([offer(quantity=2, section="C", row="8", price_per_ticket=120),
                  offer(quantity=2, section="C", row="9", price_per_ticket=125)], SKZ)
    assert not r["matches"]
    assert len(r["split_options"]) == 1
    sp = r["split_options"][0]
    assert sp["requires_approval"] is True and sp["total"] == 490.0


def test_split_not_offered_when_full_adjacent_set_exists():
    r = evaluate([offer(), offer(quantity=2, row="8"), offer(quantity=2, row="9")], SKZ)
    assert r["matches"] and r["split_options"] == []


def test_split_respects_budget():
    r = evaluate([offer(quantity=2, price_per_ticket=150), offer(quantity=2, row="2", price_per_ticket=150)], SKZ,
                 global_remaining=590)
    assert r["split_options"] == []


def test_split_disabled_for_oasis():
    r = evaluate([offer(quantity=1), offer(quantity=1, row="2")], OASIS)
    assert r["split_options"] == []


def test_ranking_prefers_better_view_and_price():
    good = offer(section="GOOD", price_per_ticket=110, view_score=5, location_score=5)
    bad = offer(section="BAD", price_per_ticket=140, view_score=2, location_score=2)
    r = evaluate([bad, good], SKZ)
    assert [m["section"] for m in r["matches"]] == ["GOOD", "BAD"]


def test_score_uses_only_known_fields():
    s, basis = score(offer(view_score=None, location_score=None), SKZ)
    assert set(basis) == {"מחיר", "סמיכות"}
    s2, basis2 = score({"price_per_ticket": None}, SKZ)
    assert s2 == 0 and basis2 == []


def test_fees_not_included_warning():
    r = evaluate([offer(fees_included=False)], SKZ)
    assert any("עמלות" in w for w in r["matches"][0]["warnings"])


def test_oasis_two_tickets_budget():
    assert evaluate([offer(quantity=2, price_per_ticket=150)], OASIS)["matches"]
    assert not evaluate([offer(quantity=2, price_per_ticket=151)], OASIS)["matches"]


def test_global_budget_summary():
    evs = [SimpleNamespace(max_total=600), SimpleNamespace(max_total=300)]
    assert budget_summary(evs, 900) == {"global_budget": 900, "allocated": 900, "ok": True, "remaining": 0}
    assert budget_summary(evs, 800)["ok"] is False
