# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Windows desktop app that automates bulk actions in the Israeli Welfare Ministry's
Salesforce instance (`welfareministry.lightning.force.com`) from Excel input.
A PySide6/pyvisual GUI loads an Excel file and config, then runs one of three
automation processes against Salesforce (auto-login with TOTP/MFA included).

The codebase was refactored in 2026. Much of the UI/Salesforce interaction logic
(XPath selectors, `sleep` timings) was extracted **verbatim** from the original
code and is intentionally frozen — see Constraints below.

## Commands

Run the app (from project root, with `config.ini` present):
```bash
python -m src.main
```

Setup:
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

There is no test suite, linter, or build step configured.

## Prerequisites / Runtime Environment

- Windows (uses `ctypes.windll` for error dialogs).
- Python 3.10+.
- Google Chrome installed, plus a matching `chromedriver.exe` at the hardcoded
  path `C:\chromedriver\chromedriver.exe` (see `driver_manager.py`). chromedriver
  is launched as a subprocess on port 9515 and Selenium connects via
  `webdriver.Remote` to `http://127.0.0.1:9515`.
- `config.ini` at the project root (create from `config.ini.example`). Loaded by a
  singleton `Config` (`src/core/config.py`); contains Salesforce credentials and
  `SECRET_KEY` (the TOTP seed for MFA). This file is gitignored — never commit it.

## Architecture

### Config-driven process selection (`TYPE`)
The `[Salesforce] TYPE` value in `config.ini` selects which processor runs. This is
the central switch the whole app pivots on:
- **TYPE 1** — `LoginProcessor`: login + per-row Selenium UI actions (search, create
  actions, create reports). The row's `סוג` (kind) column further branches into 6
  sub-flows.
- **TYPE 2** — `CandidateProcessor`: login + bulk-add candidates by ID via the UI.
- **TYPE 3** — `AttendanceProcessor`: login + attendance matrix via the **Aura API**
  (no per-row UI clicking). TYPE 3 does not require a pre-selected file in the same
  way (see `WorkerManager.start`).

`Config.validate()` enforces different required fields per TYPE.

### Threading & UI flow
The GUI must never block, so automation runs on a `QThread`:

```
main.py → Controller → WorkerManager → AutomationWorker(QThread) → <Processor>
```

- `Controller` (`src/ui/controller.py`) is a thin coordinator. It delegates to
  `SettingsController` (settings window) and `WorkerManager` (thread lifecycle).
- `WorkerManager` (`src/ui/worker_manager.py`) validates config, picks the processor
  class by TYPE, creates the worker, moves it to a `QThread`, and wires signals.
- `AutomationWorker` (`src/ui/worker.py`) instantiates the processor with a
  `WorkerSignals` object and calls `processor.process(...)`. Processors emit
  `progress`/`status`/`finished` signals back to the controller's Qt slots.

### Processors (`src/automation/processors/`)
All inherit `BaseProcessor`, which owns the shared driver lifecycle
(`_setup_driver` / `_cleanup_driver` / `_force_close_driver`), the Salesforce
`_login()` sequence (credentials + `pyotp` TOTP), and `_read_excel()`. Each concrete
processor implements `process(uploaded_file_path)`.

### Two automation strategies
- **UI-driven (TYPE 1, 2):** Selenium clicks through the Lightning UI using XPaths
  from `src/automation/selectors.py`. Reusable steps live in `src/automation/actions.py`.
- **API-driven (TYPE 3):** `SalesforceApiClient` (`src/automation/api_client.py`)
  posts Aura RPC requests via `driver.execute_async_script` (`fetch` from the page
  context, reusing the logged-in session/token). It strips the Salesforce JSON-hijack
  prefix (`*/` / `while(1);`) from responses. `ExcelParser.parse_attendance_matrix`
  reads a grid (A1 = `HH:MM|HH:MM`, dates across row 1, IDs down column A, any
  non-empty cell = present).

### Responsive stop mechanism (important)
Stopping mid-run is a core feature. The pattern, used throughout actions/processors:
- `verify_running(lambda: self.is_stopped)` is called between every Selenium step and
  raises `StopException` if the user pressed stop.
- `smart_sleep(duration, check_stop)` (`src/core/utils.py`) sleeps in small intervals,
  re-checking the stop flag — use it instead of `time.sleep` so long waits remain
  interruptible.
- On stop, processors also call `_force_close_driver()` to break any blocking Selenium
  wait that isn't between checks.

When adding automation steps, thread the `check_stop` callback through and call
`verify_running` / `smart_sleep` so the stop button keeps working.

## Constraints (from README and code comments)

- **Do not modify XPath selectors** in `selectors.py` unless Salesforce's DOM
  actually changed. They are extracted verbatim and small changes silently break runs.
- **Do not shorten wait/sleep timings.** They are tuned for Salesforce Lightning load
  behavior and are load-bearing for stability.
- Excel column access uses **Hebrew header names** (e.g. `row['תעודות זהות']`,
  `row['סוג']`, `row['תאריך']`). Many user-facing status strings are Hebrew too.
