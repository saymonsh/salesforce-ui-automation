"""Self-check for the TYPE 1 "סוג" recipe table — no framework.

    python tests/test_type1_recipes.py

Guards the picker's single source of truth (``TYPE1_RECIPES`` in data_grid)
against drift and the invariants we rely on, decoded from ``actions.py``:
  * codes are exactly 1–6,
  * every service is a known service ("act" / "pp"),
  * no code reports two services — Salesforce allows only one report per row,
  * every code actually does something,
  * the chip text the picker renders matches the verb-grouped wording.
A change that violates any of these fails loudly here instead of silently
showing the operator the wrong action.
"""
from src.ui.data_grid import TYPE1_RECIPES, _SVC_LABEL, _recipe_chips


def main() -> None:
    assert set(TYPE1_RECIPES) == {"1", "2", "3", "4", "5", "6"}, set(TYPE1_RECIPES)

    for code, rec in TYPE1_RECIPES.items():
        assert set(rec) == {"plan", "report"}, (code, rec)
        for svc in rec["plan"] + rec["report"]:
            assert svc in _SVC_LABEL, (code, svc)
        assert len(rec["report"]) <= 1, f"סוג {code}: no double-report allowed"
        assert rec["plan"] or rec["report"], f"סוג {code}: does nothing"

    # Exact engine mapping (spot-check the two endpoints decoded from actions.py).
    assert TYPE1_RECIPES["1"] == {"plan": ["act", "pp"], "report": ["pp"]}
    assert TYPE1_RECIPES["6"] == {"plan": [], "report": ["act"]}

    # Chip wording is verb-grouped and derived, not hand-written.
    assert _recipe_chips("1") == [
        ("plan", "תכנון: פעילות, תוכנית אישית"),
        ("report", "דיווח: תוכנית אישית"),
    ]
    assert _recipe_chips("6") == [("report", "דיווח: פעילות")]
    assert _recipe_chips("7") is None  # unknown code → no chips (paste guard)

    print("OK: TYPE1_RECIPES invariants hold")


if __name__ == "__main__":
    main()
