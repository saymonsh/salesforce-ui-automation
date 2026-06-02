# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows desktop app that automates the Israeli Welfare Ministry's Salesforce Lightning UI (`welfareministry.lightning.force.com`) to perform bulk actions driven by an Excel file — one Salesforce operation per row. It logs in (username/password + TOTP MFA), then iterates rows to create activities/reports or add candidates to a service schedule. The UI is in Hebrew (RTL).

## Commands

Run from the project root (the directory containing `config.ini`):

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m src.main          # launch the app
```

There is no test suite, linter, or build step configured. `python -m src.main` is the only entry point.

## Runtime prerequisites (these cause startup/runtime failures if missing)

- `config.ini` must exist in the project root (copy `config.ini.example`). Missing/invalid config raises at import time because `config_instance = Config()` is constructed eagerly at module load (`src/core/config.py:98`), and `main()` surfaces it via a Windows `MessageBoxW`.
- `chromedriver.exe` must be at the hardcoded path `C:\chromedriver\chromedriver.exe` and match the installed Chrome version. It is launched as a subprocess on `--port=9515` (`src/automation/driver_manager.py:22`).

## Architecture

Three layers, strictly separated:

**`src/ui/` — Flet desktop UI (MVC).** Note: the README says PySide6/PyVisual, but the code actually uses **Flet** (`flet` in requirements, `ft.app` in `src/main.py`). Trust the code.
- `controller.py` is a thin coordinator delegating to `SettingsController` and `WorkerManager`.
- `worker_manager.py` picks the processor based on `config.TYPE` and runs it on a daemon `threading.Thread`.
- `worker.py` defines a custom signal/slot system (`_Emitter`/`WorkerSignals` with `.connect`/`.emit`) — **not** Qt despite the naming. The worker runs the processor, catches `StopRequestedException` as a *successful* stop, and **always** emits `finished` and closes the driver in a `finally` block.
- UI updates from the worker thread are marshaled back onto Flet's event loop via `page.run_task(...)` in `controller.py`.

**`src/automation/` — Selenium engine.**
- `processors/` — one class per process `TYPE`, all extending `BaseProcessor`:
  - `LoginProcessor` (TYPE=1): per row, dispatches on the Excel `סוג` (type) column (values 1–6) to combinations of `perform_search` / `create_actions` / `create_report`.
  - `CandidateProcessor` (TYPE=2): adds candidates to a service schedule by ID number.
  - `AttendanceProcessor` (TYPE=3): fills an attendance matrix via the **Aura API** instead of per-row UI clicking.
- `BaseProcessor` owns the shared driver lifecycle (`_setup_driver`), the full login+TOTP flow (`_login`), Excel reading (`_read_excel`), and the cooperative stop mechanism.
- `actions.py` — the low-level Selenium step functions used by `LoginProcessor`.
- `selectors.py` — all XPath selectors, centralized.
- `api_client.py` — `SalesforceApiClient` posts Aura RPC requests via `driver.execute_async_script` (`fetch` from the page context, reusing the logged-in session/token) and strips the Salesforce JSON-hijack prefix (`*/`, `while(1);`) from responses. Used by TYPE 3.
- `excel_parser.py` — `ExcelParser.parse_attendance_matrix` reads the TYPE 3 grid (A1 = `HH:MM|HH:MM`, dates across row 1, IDs down column A, any non-empty cell = present).
- `driver_manager.py` — launches chromedriver subprocess, creates a `webdriver.Remote` against `127.0.0.1:9515`, strips proxy env vars, and force-terminates both driver and subprocess on close.

**`src/core/` — config, constants, utils, exceptions.**
- `config.py` — singleton `Config` reading `config.ini`; `config_instance` is the global imported everywhere as `parm`. `validate()` returns context-aware missing-field lists keyed off `TYPE`.

## Critical constraints (do not "clean up" these)

- **Selectors and wait timings are load-bearing.** XPaths in `selectors.py` and the `sleep`/timeout values in `actions.py` are tuned against Salesforce's live DOM and must not be shortened or changed unless the Salesforce UI itself changed. The files carry explicit "do not modify" banners.
- **Clicks use `driver.execute_script("arguments[0].click();", el)`** in many places instead of `.click()` — this is a deliberate workaround for `ElementClickInterceptedException`. Keep it.
- **The stop mechanism is cooperative and interruptible.** Never use bare `time.sleep` or blocking `WebDriverWait`/`find_element` in automation code. Use the wrappers in `src/core/utils.py`:
  - `smart_sleep(duration, check_stop)` instead of `sleep`
  - `interruptible_find_element(...)` / `interruptible_wait(...)` instead of `driver.find_element` / `WebDriverWait`
  - call `verify_running(check_stop)` / `self.check_for_stop()` between steps

  These poll a `threading.Event` and raise `StopRequestedException` so the user's Stop button takes effect mid-flight (including during long waits). Processors thread the stop check through as `check_stop_func=lambda: self.is_stopped`.

## Excel input

Sheets are read with pandas/openpyxl. Column headers are **Hebrew** and accessed by literal string: `row['תעודות זהות']` (ID number), `row['סוג']` (type), `row['תאריך']` (date). The `סוג` value drives which automation steps run in `LoginProcessor`.

## Process types (`config.TYPE`)

- `1` → `LoginProcessor` (requires Excel path, Activity NUMBER, DESCRIPTION)
- `2` → `CandidateProcessor` (requires Excel path)
- `3` → `AttendanceProcessor` (no pre-selected file required in the same way — see the `worker_manager.start` guard): fills an attendance matrix via the Aura API.
