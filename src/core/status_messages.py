"""Status channel strings — the high-level, Hebrew, operator-facing messages
(issue #12). This is the single source of truth for the copy spec in
``docs/logging-channels.md``.

These are the *only* strings that reach the status field. They are deliberately
separate from the debug channel (``src/core/logger.py``), which is English and
technical. Because this channel is clean by construction, no noise filter is
needed on the UI side.

Numbers and IDs are wrapped in an LTR isolate (U+2066 … U+2069) so digits render
left-to-right inside the Hebrew RTL line *and* don't drag adjacent neutrals
(parentheses, ":", "-") out of place. Always interpolate via ``_iso`` / the
helpers below — never f-string a raw number into a Hebrew status string. The
implementation lives in ``src.core.utils.ltr_isolate`` so the same primitive is
shared with the UI layer.
"""
from __future__ import annotations

from src.core.utils import ltr_isolate as _iso


class Status:
    """Status-channel copy. Constants are static; methods interpolate."""

    # --- shared across all process types ------------------------------------
    # Input is the in-app entry grid (epic #14). FILE_EMPTY still applies: a grid
    # source can yield zero rows just like an empty file, and the empty-source
    # guard in BaseProcessor reports it.
    FILE_EMPTY = "אין שורות לעיבוד"
    MANUAL_EMPTY = "הזן נתונים בטבלת ההזנה כדי להתחיל"
    MANUAL_INVALID = "יש שורות פגומות בטבלה — תקן אותן כדי להריץ"
    SAVED = "ההגדרות נשמרו"
    LOGGING_IN = "מתחבר ל-Salesforce…"
    MFA_OK = "האימות הדו-שלבי עבר — מתחבר"
    STOPPING = "עוצר…"
    STOPPED_PLAIN = "התהליך נעצר"

    # End-of-run completion dialog (reuses the same alert component as a failure —
    # one unified "system message" language for both outcomes). Title + a body
    # built from the run summary by ``completion_body`` below.
    COMPLETED_TITLE = "הריצה הושלמה"

    @staticmethod
    def failed_rows_title(n: int) -> str:
        return f"{_iso(n)} שורות נכשלו ולא דווחו:"

    @staticmethod
    def missing_ids_title(n: int) -> str:
        return f"{_iso(n)} ת.ז. לא אותרו ולא עודכנו:"

    @staticmethod
    def completion_body(summary: dict) -> str:
        """Build the success-dialog body from a run summary dict.

        Shape: ``{"success_text": str, "problems_title": str?, "problem_ids": [..],
        "sections": [{"title": str, "ids": [..]} | {"title": str, "lines": [..]}]}``.
        The success line always shows; the legacy problems block (failed rows in
        TYPE 1, unmatched IDs in TYPE 2/3) is appended when present; then any extra
        ``sections`` (the TYPE 3 compare/upsert report) are appended in order. A
        section carries either ``ids`` (short tokens joined by " · ", each
        LTR-isolated) or ``lines`` (pre-formatted strings, one per line — used for
        rows that already mix Hebrew and isolated numbers). IDs are LTR-isolated so
        digits render correctly inside the RTL prose.
        """
        body = summary.get("success_text", "")
        title = summary.get("problems_title")
        if title:
            ids = summary.get("problem_ids") or []
            body += "\n\n" + title + "\n" + " · ".join(_iso(str(x)) for x in ids)
        for sec in summary.get("sections") or []:
            body += "\n\n" + sec["title"]
            lines = sec.get("lines")
            if lines:
                body += "\n" + "\n".join(lines)
            else:
                ids = sec.get("ids") or []
                if ids:
                    body += "\n" + " · ".join(_iso(str(x)) for x in ids)
        return body

    @staticmethod
    def stopped(done: int | None = None, total: int | None = None) -> str:
        # Row-based types (1/2) report progress; date-based type 3 has no row
        # counters, so fall back to a plain "stopped".
        if total and total > 0:
            return f"התהליך נעצר — {_iso(done or 0)} מתוך {_iso(total)} הושלמו"
        return Status.STOPPED_PLAIN

    @staticmethod
    def fatal_error(reason: str) -> str:
        # `reason` is already an operator-facing Hebrew message
        # (see src/core/error_messages.humanize_error) — not LRM-wrapped, since
        # it is RTL prose, not a number/ID.
        return f"התהליך נכשל: {reason}"

    # --- TYPE 1 — דיווח פעילות ----------------------------------------------
    @staticmethod
    def t1_processing(n: int, total: int, id_number, type_value) -> str:
        return (
            f"מעבד שורה {_iso(n)} מתוך {_iso(total)} — "
            f"ת.ז. {_iso(id_number)} (סוג {_iso(type_value)})"
        )

    @staticmethod
    def t1_done(total: int) -> str:
        return f"הסתיים — {_iso(total)} שורות עובדו"

    @staticmethod
    def t1_summary(ok: int) -> str:
        # Success line for the completion dialog / summary card — counts only the
        # rows that actually succeeded (failed rows are listed separately).
        return f"{_iso(ok)} שורות עובדו בהצלחה"

    # --- TYPE 2 — מועמדים (end state requires manual action → warning) -------
    @staticmethod
    def t2_processing(n: int, total: int, id_number) -> str:
        return f"מוסיף מועמד {_iso(n)} מתוך {_iso(total)} — ת.ז. {_iso(id_number)}"

    @staticmethod
    def t2_summary(ok: int) -> str:
        # Success line for the completion dialog when some candidates were skipped
        # (counts only those actually added; skipped IDs are listed separately).
        return f"{_iso(ok)} מועמדים נוספו בהצלחה"

    @staticmethod
    def t2_done(total: int) -> str:
        # The run ends in the 'action required' state with Chrome left open
        # (embedded in the panel) so the operator can finish the manual save, then
        # close it via the panel's "done" button. Remind them — that browser holds
        # a logged-in Salesforce session. The critical 'הבא' instruction stays
        # first so an ellipsised one-liner still shows it.
        return f"נוספו {_iso(total)} מועמדים — לחץ 'הבא' ב-Salesforce לשמירה, וסגור את החלון בסיום"

    # --- TYPE 3 — נוכחות (unit is a date/session, not a row) ----------------
    @staticmethod
    def t3_processing(date_str: str, n: int, total: int) -> str:
        # date_str must already be Israeli d.m.yyyy — every date in the UI is
        # day-first, never ISO. The caller converts before passing it in.
        return f"מעבד תאריך {_iso(date_str)} ({_iso(n)} מתוך {_iso(total)})"

    @staticmethod
    def t3_done(n: int) -> str:
        return f"נוצרו {_iso(n)} מפגשים"

    @staticmethod
    def t3_summary(sessions: int) -> str:
        # Success line for the completion dialog / summary card (TYPE 3).
        return f"{_iso(sessions)} מפגשים נוצרו ודווחו בהצלחה"

    @staticmethod
    def t3_missing(missing_ids: list[str]) -> str:
        # Count only — the full ID list lives in the persistent run-summary card,
        # so this stays short enough never to truncate on the one-line status field.
        return f"שים לב: {_iso(len(missing_ids))} ת.ז. לא אותרו ולא עודכנו — ראה כרטיס סיכום"

    # --- TYPE 3, mode 2 — השוואה בלבד (read-only compare) -------------------
    @staticmethod
    def t3_cmp_processing(date_str: str, n: int, total: int) -> str:
        # "בודק" (checking), not "מעבד" (processing) — reassures the operator that
        # compare mode only reads and never writes. date_str is Israeli d.m.yyyy.
        return f"בודק תאריך {_iso(date_str)} ({_iso(n)} מתוך {_iso(total)})"

    @staticmethod
    def t3_cmp_done(n_diffs: int) -> str:
        if n_diffs == 0:
            return "ההשוואה הסתיימה — הגריד תואם למערכת, אין הבדלים"
        return f"ההשוואה הסתיימה — נמצאו {_iso(n_diffs)} הבדלים (ראה סיכום)"

    @staticmethod
    def t3_cmp_summary(n_diffs: int) -> str:
        # Headline line for the completion dialog (read-only — nothing changed).
        if n_diffs == 0:
            return "ההשוואה הסתיימה — הגריד תואם למערכת. לא בוצע שום שינוי."
        return f"ההשוואה הסתיימה — נמצאו {_iso(n_diffs)} הבדלים. לא בוצע שום שינוי במערכת."

    @staticmethod
    def cmp_dates_only_grid_title(n: int) -> str:
        return f"תאריכים בגריד שאין להם מפגש במערכת ({_iso(n)}):"

    @staticmethod
    def cmp_dates_only_sf_title(n: int) -> str:
        return f"מפגשים במערכת בתאריכים שאינם בגריד ({_iso(n)}):"

    @staticmethod
    def cmp_unreported_dates_title(n: int) -> str:
        return f"מפגשים שקיימים אך טרם דווחה בהם נוכחות ({_iso(n)}):"

    @staticmethod
    def cmp_duplicate_dates_title(n: int) -> str:
        return f"תאריכים עם יותר ממפגש אחד — לא נבדקו ({_iso(n)}):"

    @staticmethod
    def cmp_mismatch_title(n: int) -> str:
        return f"אי-התאמות בנוכחות בין הגריד למערכת ({_iso(n)}):"

    @staticmethod
    def cmp_mismatch_line(date_str: str, id_number, grid_status: str, sf_status: str | None) -> str:
        # One mismatch row, pre-formatted (date + ת.ז. isolated, statuses are
        # Hebrew prose). sf_status None ⇒ no attendance reported in SF for that row.
        sf_txt = sf_status if sf_status else "לא דווח"
        return f"{_iso(date_str)} · ת.ז. {_iso(id_number)} — גריד: {grid_status}, מערכת: {sf_txt}"

    @staticmethod
    def cmp_missing_ids_title(n: int) -> str:
        return f"ת.ז. בגריד שאינם רשומים בקורס ({_iso(n)}):"

    @staticmethod
    def cmp_sf_only_title(n: int) -> str:
        return f"משתתפים רשומים בקורס שאינם בגריד ({_iso(n)}):"

    # --- TYPE 3, mode 3 — עדכון והשלמה (upsert) -----------------------------
    @staticmethod
    def t3_upsert_done(created: int, updated: int, unchanged: int) -> str:
        return f"הסתיים — נוצרו {_iso(created)}, עודכנו {_iso(updated)}, ללא שינוי {_iso(unchanged)}"

    @staticmethod
    def t3_upsert_summary(created: int, updated: int, unchanged: int) -> str:
        return (
            f"נוצרו {_iso(created)} מפגשים, עודכנו {_iso(updated)}, "
            f"ו-{_iso(unchanged)} כבר היו תואמים. שום דבר אחר לא שונה."
        )


# --------------------------------------------------------------------- self-check
# Runnable check (no framework): `python -m src.core.status_messages`.
# Guards the completion-dialog body builder — the one piece of non-trivial logic
# here (clean success vs. partial success with a listed problem block).
if __name__ == "__main__":
    clean = Status.completion_body({"success_text": Status.t1_summary(12)})
    assert "12" in clean and "בהצלחה" in clean, clean
    assert "נכשלו" not in clean, clean  # no problem block when nothing failed

    partial = Status.completion_body({
        "success_text": Status.t1_summary(9),
        "problems_title": Status.failed_rows_title(3),
        "problem_ids": ["311111111", "305554321"],
    })
    assert "9" in partial and "נכשלו" in partial, partial
    assert "311111111" in partial and "305554321" in partial, partial

    # TYPE 2 partial run: skipped candidates listed via the shared problem block.
    t2 = Status.completion_body({
        "success_text": Status.t2_summary(4),
        "problems_title": Status.missing_ids_title(1),
        "problem_ids": ["322222222"],
    })
    assert "4" in t2 and "נוספו" in t2 and "322222222" in t2, t2

    # TYPE 3 compare report: multi-section body with both `ids` and `lines`.
    cmp = Status.completion_body({
        "success_text": Status.t3_cmp_summary(2),
        "sections": [
            {"title": Status.cmp_dates_only_grid_title(1), "ids": ["18.1.2026"]},
            {"title": Status.cmp_mismatch_title(1),
             "lines": [Status.cmp_mismatch_line("18.1.2026", "311111111", "נוכח", None)]},
            {"title": Status.cmp_sf_only_title(1), "ids": ["322222222"]},
        ],
    })
    assert "לא בוצע" in cmp, cmp                      # read-only reassurance present
    assert "18.1.2026" in cmp and "311111111" in cmp, cmp
    assert "לא דווח" in cmp and "322222222" in cmp, cmp
    # empty `sections`/`ids` must not break or emit a dangling title:
    assert Status.completion_body({"success_text": "x", "sections": []}) == "x"
    print("OK — completion_body builds clean + partial + compare-report summaries")
