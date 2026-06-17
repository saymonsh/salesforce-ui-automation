# TYPE 3 (attendance) — compare & upsert sub-modes

TYPE 3 fills the Welfare Ministry's group-attendance matrix into Salesforce via
the Aura API. It has **two sub-modes**, chosen by the `[Salesforce] T3_MODE`
config key (surfaced as a selector in the settings panel when TYPE 3 is picked):

| `T3_MODE` | Label | What it does | Writes? |
|---|---|---|---|
| `compare` | השוואה בלבד | Read existing SF attendance, diff it against the grid, report the differences. | **none** |
| `upsert` | עדכון והשלמה | Create missing sessions and sync attendance to the grid (delta only). | yes |

There is deliberately **no "mode 1"** — the old blind-create behaviour was
removed (it created duplicate sessions on re-run and could not fix existing
data). `upsert` is its strict superset.

> Legacy `config.ini` files that stored `T3_MODE = 2`/`3` still work: `config.py`
> maps `2 → compare`, `3 → upsert`, and the value auto-migrates to the named form
> on the next settings save.

The constants live in [`src/core/constants.py`](../src/core/constants.py)
(`T3_MODE_COMPARE` / `T3_MODE_UPSERT`); dispatch is in
[`AttendanceProcessor.process`](../src/automation/processors/attendance_processor.py).

---

## The data model & the join

The grid is keyed by **ID number** (תעודת זהות). Salesforce is not:

```
grid row  ──(id_number)──▶  Pa_Service_Participant__c   (enrolled on the COURSE)
                                      │ participant SF id
                                      ▼
                           Service_Delivery__c          (one attendance row per
                                                          participant per SESSION)
```

A `Service_Delivery__c` row carries `Pa_Service_Participant__c` (the participant
SF id) and `Pa_Action_Status__c` — **not** the ID number. So every comparison
joins through `get_participants` (ID number ↔ participant SF id), which is the
only bridge between the grid and SF.

### Read layer (read-only, used by both modes)

All three are read-only `RelatedListUiController/postRelatedListRecords` calls in
[`api_client.py`](../src/automation/api_client.py):

| Method | Reads | Related list |
|---|---|---|
| `get_participants(schedule)` | ID number → participant SF id | `Service_Deliveries__r` on the schedule |
| `get_sessions(schedule)` | existing sessions + start datetime | `Service_Sessions__r` on the schedule |
| `get_service_deliveries(session)` | attendance rows (`Service_Delivery__c`) | `Service_Deliveries__r` on the session |

Session start datetimes are stored **UTC**; grid dates are **Israel-local**. Dates
are matched after converting UTC → `Asia/Jerusalem` (`_utc_to_israel_date`), so a
session late in the UTC day lands on the correct Israeli date.

---

## ⚠️ Why compare mode never opens the flow

Per-participant `Service_Delivery__c` rows are **not** auto-created with a session.
They are created by the `Pa_Create_Service_Delivery` quick-action flow — and
**opening that flow (`startFlow`) creates and commits the rows immediately**, even
if the operator changes nothing and closes the screen with ✕. (Proven from a HAR:
opening an empty session returned 20 rows with `CreatedDate` = now, no cleanup
call on ✕.)

Therefore **compare mode must never touch the flow.** It reads existing rows via
`get_service_deliveries` (a related-list read — returns an empty list for a
never-reported session, creating nothing). The flow is used **only** on the write
path (`upsert`).

---

## Mode: `compare` (read-only)

[`_run_compare`](../src/automation/processors/attendance_processor.py). Reads
participants, sessions, and the attendance of each grid date that maps to exactly
one session, then reports (zero writes):

| Section | Meaning |
|---|---|
| תאריכים בגריד שאין להם מפגש במערכת | grid dates with no SF session |
| מפגשים שקיימים אך טרם דווחה בהם נוכחות | session exists but has no reported attendance (collapsed to one line, not a per-participant flood) |
| מפגשים במערכת בתאריכים שאינם בגריד | SF sessions on dates not in the grid |
| תאריכים עם יותר ממפגש אחד — לא נבדקו | ambiguous (>1 session on a date) |
| אי-התאמות בנוכחות בין הגריד למערכת | per-participant status mismatch (`grid` vs `מערכת`; `לא דווח` = no SF status) |
| ת.ז. בגריד שאינם רשומים בקורס | grid IDs not enrolled on the course |
| משתתפים רשומים בקורס שאינם בגריד | course participants absent from the grid |

The compare report **is the preview of what `upsert` will do** (missing dates →
created; mismatches → fixed).

---

## Mode: `upsert` (read-first, write only the deltas)

[`_run_upsert`](../src/automation/processors/attendance_processor.py). Per grid
date:

1. **No session** → `create_session` → `_apply_via_flow` (the flow creates the
   rows; all are reported). Counted **created**.
2. **Session exists** → read its attendance first (`get_service_deliveries`,
   read-only) and compute the delta:
   - already matches the grid → **skip, zero writes**. Counted **unchanged**.
   - differs (status change, missing row, or unreported) → `_apply_via_flow`.
     Counted **updated**.
3. **Ambiguous** (same date in >1 grid column, or >1 SF session) → skip + report,
   never written (`compute_ambiguous_dates`). Guards against creating a second
   session for a repeated date.

`_apply_via_flow` is the proven 1:1 manual sequence: `start_create_sd_flow` →
`report_attendance` (changed rows only) → `finish_create_sd_flow`.

**Attendance value rules:** `נוכח` / `לא נוכח`; absent ⇒ `Pa_No_Action_Reason__c =
"אחר"`; present ⇒ the reason is cleared (Salesforce rejects a present row carrying
a reason) — but the explicit null is sent only when a reason is actually present,
so a fresh/already-present row keeps the exact payload the create path was
validated with.

Because it reads before writing, `upsert` is **idempotent**: a second run with no
grid changes converges to `0 created, 0 updated, all unchanged`.

---

## Output & safety notes

- Both modes report through the single completion dialog
  ([`Status.completion_body`](../src/core/status_messages.py) gained an additive
  multi-section path); the full report is copyable.
- Aura calls are paced with human-like pauses (`_human_pause`) in **both** modes,
  so a burst of reads can't look like rapid-fire automation. Pauses are
  interruptible by the Stop button (`smart_sleep`).
- `get_participants` normalises IDs to 9 digits to match the grid's `zfill(9)`.
- The pure decision logic (`compute_compare`, `compute_delta`,
  `compute_ambiguous_dates`, date matching) has a framework-free self-check:
  `python -m src.automation.processors.attendance_processor`.

**Production constraint:** every call hits production. Mode `compare` is read-only
and safe to run live; mode `upsert` writes (validated live, idempotent). The org
blocks foreign IPs — **disconnect VPN before running** or login fails with a
"security policy" banner.
