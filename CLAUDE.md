# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Desktop GUI app that automates the Salesforce Lightning UI for the Israeli Welfare Ministry (`welfareministry.lightning.force.com`). It drives a real Chrome browser via Selenium to perform bulk actions (login + create activities/reports, or add candidates) row-by-row from an Excel file. Much of the UI/business logic is Hebrew; Excel column names and Salesforce element text are Hebrew strings (e.g. `'תעודות זהות'`, `'סוג'`, `'תאריך'`).

## Commands

```powershell
# Setup (Windows / PowerShell)
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Run the app (must run as a module from the project root)
python -m src.main
```

- There are **no tests, linters, or build steps** in this repo.
- Requires `config.ini` at the project root (copy from `config.ini.example`). The app shows a Windows MessageBox and exits if it's missing.

## Runtime prerequisites (hard-coded, environment-specific)

- **ChromeDriver must exist at `C:\chromedriver\chromedriver.exe`** and match the installed Chrome version. The path is hard-coded in `src/automation/driver_manager.py`; chromedriver is launched as a subprocess on **port 9515** and Selenium connects to it as a `webdriver.Remote` at `http://127.0.0.1:9515`.
- Windows-only (uses `ctypes.windll` for error dialogs).

## Architecture

Three layers under `src/`, wired together in `src/main.py`:

1. **`ui/`** — PySide6/pyvisual desktop app (MVC).
   - `main_window.py` / `settings_window.py` are pure **View** (build widgets only).
   - `controller.py` is a thin coordinator delegating to `SettingsController` and `WorkerManager`.
   - `worker_manager.py` + `worker.py` run automation on a **separate `QThread`** so the GUI never blocks. `AutomationWorker` instantiates a processor class and calls `.process()`; it communicates back via Qt `WorkerSignals` (`finished`, `progress`, `status`, `error`).

2. **`automation/`** — Selenium engine.
   - `driver_manager.py` — chromedriver subprocess + driver creation (disables notifications/popups/cookies, clears proxy env vars).
   - `processors/` — one class per run **TYPE**, all extending `BaseProcessor` (ABC). `BaseProcessor` owns the shared driver lifecycle (`_setup_driver`, `_cleanup_driver`, `_force_close_driver`), the full login+TOTP flow (`_login`), and Excel reading (`_read_excel`).
     - `LoginProcessor` (config TYPE=1): per Excel row, runs `perform_search` → `create_actions` / `create_report` depending on the row's `'סוג'` value (1–6).
     - `CandidateProcessor` (config TYPE=2): adds candidates by ID number, using clipboard paste (`pyperclip`) into a search box.
   - `actions.py` — the search/create-action/create-report Selenium step sequences used by `LoginProcessor`.
   - `selectors.py` — **all** XPath selectors live here as constants.

3. **`core/`** — cross-cutting.
   - `config.py` — `Config` **singleton** (`config_instance`) reading `config.ini`. Exposes `USER_NAME`, `PASSWORD`, `SECRET_KEY`, `URL`, `TYPE` (int), `ACT_DESCRIPTION`, `ACT_NU`, `UPLOADED_FILE_PATH`. `validate()` does TYPE-aware checks; `update_config()` writes back to the file and reloads.
   - `constants.py` — asset paths (fonts/icons) and UI colors.
   - `utils.py` — `verify_running` / `smart_sleep` (the stop mechanism, see below).
   - `exceptions.py` — `StopException`.

### config TYPE drives behavior

`config.ini` `[Salesforce] TYPE` selects which processor runs (set via the Settings window). `1` = Login & Actions, `2` = Add Candidates. `WorkerManager.start()` maps TYPE → processor class and validates required fields per TYPE.

### Responsive stop mechanism

Stop must interrupt long Selenium waits. The pattern, used pervasively, is:
- The processor holds an `is_stopped` flag; the UI's Stop button calls `worker.stop()` → `processor.stop()`, which sets the flag **and** force-quits the driver to break any blocking wait.
- Automation code calls `verify_running(lambda: self.is_stopped)` between steps and uses `smart_sleep(seconds, check)` instead of `time.sleep` — both raise `StopException` when stopped. **Use these, never raw `time.sleep`, in automation paths.**

## Important constraints

- **Do not modify XPath selectors in `selectors.py`** unless the Salesforce DOM actually changed — they are matched verbatim to the live UI. The login flow XPaths in `BaseProcessor._login` are equally load-bearing.
- **Do not shorten waits** (`smart_sleep` durations, `implicitly_wait(30)`, `WebDriverWait(..., 30)`). They are tuned for Salesforce Lightning's load timing and are critical for stability.
- `config.ini` is gitignored and contains real credentials + a TOTP `SECRET_KEY` (used by `pyotp` for MFA). Never commit it.
- `perform_search` in `actions.py` writes `debug_search_error.png` / `debug_page_source.html` to the project root on failure — these are debug artifacts.
