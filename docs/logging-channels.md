# Logging channels — copy & format spec (issue #12)

Reference for implementing [issue #12](https://github.com/saymonsh/salesforce-ui-automation/issues/12):
separate the **user status** channel from the **debug** channel. This document is the
*copy/format* deliverable — the actual wiring (a `log` channel on `WorkerSignals`,
a central logger, replacing the ~32 `print()` calls) is the implementation step.

Two channels, deliberately different:

| Channel | Audience | Language | Where it shows |
|---|---|---|---|
| **Status** | the operator | Hebrew (RTL) | status field |
| **Debug** | developer / ops | English | terminal / activity feed |

Once these are split, the `_is_status_noise` filter in `src/ui/main_window.py` is
no longer needed — the status channel is clean by construction. Delete it.

---

## 1. Status channel (Hebrew, high-level)

Covers three process types with genuinely different units of work:

| Type | Unit of work | Identified by | End state |
|---|---|---|---|
| **1** דיווח פעילות | Excel row | ת.ז. + סוג (1–6) | finishes automatically (`success`) |
| **2** מועמדים | Excel row | ת.ז. only | **requires manual action** → `WARNING` level |
| **3** נוכחות | date / session (not a row!) | date — all participants batched | finishes + missing-IDs summary (`success`) |

### The strings

Numbers / IDs are wrapped in LRM isolates (`‪ … ‬`, U+202A … U+202C) so digits
render left-to-right inside the Hebrew RTL line — keep them when interpolating.

**Shared across all types**

| Key | Text |
|---|---|
| `no_file` | בחר קובץ Excel כדי להתחיל |
| `file_selected` | נבחר קובץ: ‪{filename}‬ |
| `file_empty` | הקובץ ריק — אין שורות לעיבוד (`error`) |
| `saved` | ההגדרות נשמרו |
| `logging_in` | מתחבר ל-Salesforce… |
| `mfa_ok` | האימות הדו-שלבי עבר — מתחבר |
| `stopping` | עוצר… |
| `stopped` | התהליך נעצר — ‪{done}‬ מתוך ‪{total}‬ הושלמו |
| `fatal_error` | התהליך נכשל: ‪{reason}‬ (`error`) |

**TYPE 1 — דיווח פעילות**

| Key | Text |
|---|---|
| `t1_processing` | מעבד שורה ‪{n}‬ מתוך ‪{total}‬ — ת.ז. ‪{id}‬ (סוג ‪{type}‬) |
| `t1_done` | הסתיים — ‪{total}‬ שורות עובדו (`success`) |

**TYPE 2 — מועמדים** (end state requires manual action → `warning`, not success)

| Key | Text |
|---|---|
| `t2_processing` | מוסיף מועמד ‪{n}‬ מתוך ‪{total}‬ — ת.ז. ‪{id}‬ |
| `t2_done` | נוספו ‪{total}‬ מועמדים — לחץ 'הבא' ב-Salesforce כדי לשמור (`warning`) |

**TYPE 3 — נוכחות** (unit is a date/session; per-date sub-steps go to debug)

| Key | Text |
|---|---|
| `t3_processing` | מעבד תאריך ‪{date}‬ (‪{n}‬ מתוך ‪{total}‬) |
| `t3_done` | נוצרו ‪{n}‬ מפגשים (`success`) |
| `t3_missing` | ⏎ שים לב: ‪{k}‬ ת.ז. לא אותרו ולא עודכנו: ‪{list}‬ |

### Decisions baked in

- **TYPE 3 sub-steps go to debug.** Only `מעבד תאריך X מתוך Y` shows in the status
  field; the per-date `create session` / `report attendance` / `finish flow` steps
  are "under the hood" → debug channel.
- **Manual-action end state is TYPE 2 only.** TYPE 3 persists everything via the API
  and does **not** need a manual "next". (The leftover `finally` line in
  `attendance_processor.py` that displayed `"אנא לחץ 'הבא' להמשך"` on every TYPE 3 run
  — including success — has been removed.)
- A new **`warning`** level is needed in `set_status` (`src/ui/main_window.py`) so the
  TYPE 2 end state renders as a warning, not a green success.
- All interpolated numbers/IDs use LRM isolates (`‪ … ‬`) for correct RTL.

---

## 2. Debug channel (English, technical)

One line per event:

```
{timestamp}  {LEVEL}  [{stage} | {context}]  {message}
```

| Field | Meaning | Example |
|---|---|---|
| `timestamp` | wall-clock | `2026-06-04 14:32:01` |
| `LEVEL` | severity | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `stage` | step running | `login`, `search`, `report`, `aura`, `attendance` |
| `context` | which row/date/id | `row 12`, `date 2026-05-01`, `id 031234567` |
| `message` | factual, focused | `clicking SEARCH_RESULT_LINK` |

### Severity levels

| Level | When | Example |
|---|---|---|
| `DEBUG` | under the hood — selector, payload, timing | `clicking SEARCH_RESULT_LINK (waited 1.2s)` |
| `INFO` | a technical milestone completed | `login OK — TOTP accepted` |
| `WARNING` | anomaly that does not stop the run | `no Service Delivery for id 031234567 — skipped` |
| `ERROR` | a failure (include traceback) | `perform_search failed: TimeoutException` |

### Examples

**TYPE 1 — דיווח פעילות**
```
2026-06-04 14:32:00  INFO   [login | -]              login OK — TOTP accepted
2026-06-04 14:32:01  INFO   [run | -]                45 rows loaded from Excel
2026-06-04 14:32:02  DEBUG  [search | row 12]        sending id 031234567, waiting SEARCH_RESULT_LINK (timeout 30s)
2026-06-04 14:32:03  DEBUG  [search | row 12]        result link clicked (1.1s)
2026-06-04 14:32:05  DEBUG  [report | row 12]        create_report type=3 date=2026-05-01
2026-06-04 14:32:09  ERROR  [report | row 14]        type=1 failed: ElementClickInterceptedException → critical, aborting
```

**TYPE 3 — נוכחות** (sub-steps moved here from the status channel)
```
2026-06-04 14:40:00  INFO   [aura | -]               participants fetched: 23
2026-06-04 14:40:01  WARNING[run | -]                2 Excel ids not found in SF: 011112222, 033334444
2026-06-04 14:40:02  DEBUG  [aura | date 2026-05-01] create_session → 200, id=a1B5g000000XyzAEAU
2026-06-04 14:40:05  DEBUG  [aura | date 2026-05-01] start_create_sd_flow → 21 delivery records
2026-06-04 14:40:09  DEBUG  [aura | date 2026-05-01] report_attendance → 200 (21 marked)
2026-06-04 14:40:11  DEBUG  [aura | date 2026-05-01] finish_create_sd_flow → done
```

### Writing guidelines

1. **Factual, not conversational** — `participants fetched: 23`, not `Got the participants successfully!`.
2. **Every line carries `context`** — always `row N` or `date X`, so a failure is traceable.
3. **Name the selector/endpoint** — `SEARCH_RESULT_LINK`, `create_session`; not "the search button".
4. **Timing in `DEBUG`** — `(1.1s)` / `(waited 1.2s)` on waiting steps; ticks are the most common stall cause.
5. **Aura result = status code + what came back** — `→ 200, id=...` / `→ 21 records`. Don't dump full JSON
   by default — only under full `DEBUG` (like the existing `print(json.dumps(...))` in `api_client.py`).
6. **English only** — where current code mixes Hebrew (`print(f"תקלה במספר זהות...")` in
   `login_processor.py`), it becomes `ERROR [run | row N] failed for id X: ...`.
