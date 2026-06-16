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
from src.ui.data_grid import TYPE1_RECIPES, _SVC_LABEL, _recipe_chips, DataGridView


def check_type_only_seed_is_ignored() -> None:
    """A new TYPE 1 row inherits the last-picked סוג (``_new_t1_row``). A row that
    carries ONLY that inherited type (no id/date) is the trailing seed — it must
    stay ignorable like a fully-empty row, or it gets flagged as a פגומה row and
    blocks the run after the first pick. Guards ``_t1_filled`` / ``_apply_type_to_all``.
    """
    grid = DataGridView(None)  # no page needed: these paths never touch it
    grid._type = "1"
    grid._t1_rows = [
        {"id": "123456789", "type": "1", "date": "16.6.2026"},  # a real, valid row
        {"id": "", "type": "1", "date": ""},                    # inherited-type seed
    ]
    assert len(grid._t1_filled()) == 1, "type-only seed must not count as a row"
    assert not grid.invalid_reasons(), grid.invalid_reasons()
    assert grid.to_source() is not None, "a valid batch + empty seed must still run"

    # A seed with nothing picked yet is empty too (no סוג inherited).
    grid._t1_rows = [{"id": "", "type": "", "date": ""}]
    assert grid.is_empty(), "all-empty grid must read as empty"


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

    check_type_only_seed_is_ignored()

    print("OK: TYPE1_RECIPES invariants hold")


if __name__ == "__main__":
    main()
