# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows desktop app that automates the Israeli Welfare Ministry's Salesforce Lightning UI (`welfareministry.lightning.force.com`) to perform bulk actions — one Salesforce operation per row, entered in the app's data-entry grid (rows are typed in or smart-pasted from Excel/Sheets; there is no Excel-*file* import — see "Input data"). It logs in (username/password + TOTP MFA), then iterates rows to create activities/reports or add candidates to a service schedule. The UI is in Hebrew (RTL).

## Commands

Run from the project root (the directory containing `config.ini`):

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m src.main          # launch the app
python -m src.main --dry_run # dry-run: full UI, no Selenium/Salesforce (see below)
python tests/test_type1_recipes.py   # run a self-check (framework-free, assert-based)
```

There is no linter. Tests are framework-free, assert-based self-checks run directly as scripts (e.g. `python tests/test_type1_recipes.py`) — there is no pytest/test runner.

**Packaging** (ADR-001): a per-user Windows installer is built with `pyinstaller build.spec` → `iscc installer.iss`. Writable files (`config.ini`, `draft.json`, logs) route through `src/core/paths.py`: project root in a source run, `%APPDATA%\WelfareSFAutomation\` in a frozen build (seeded on first launch). See `docs/packaging.md`.

**Dry-run / demo mode** (`--dry_run`, gated by `DRY_RUN` in `src/core/constants.py`): previews the whole UI with no Selenium or Salesforce. `WorkerManager` swaps in `DemoProcessor` + `DemoDriverManager`, which embed a placeholder window (e.g. mspaint) as a Chrome stand-in so the embedding/handoff flow can be exercised offline.

## Runtime prerequisites (these cause startup/runtime failures if missing)

- `config.ini` must exist where `src/core/paths.py` resolves it — the project root in a source run (copy `config.ini.example`), or `%APPDATA%\WelfareSFAutomation\` in a frozen build (auto-seeded on first launch, so a fresh install doesn't crash). Missing/invalid config still raises at import time because `config_instance = Config()` is constructed eagerly at module load (`src/core/config.py`), and `main()` surfaces it via a Windows `MessageBoxW`.
- `chromedriver` is acquired automatically by **Selenium Manager** (built into Selenium 4.6+), which resolves/downloads the build matching the installed Chrome — no hardcoded path, no fixed port (`src/automation/driver_manager.py`). It needs direct internet for the *first* fetch of a given Chrome version (then it's cached); `setup_proxy()` strips any proxy env so that fetch and the localhost WebDriver call go direct. If acquisition fails (e.g. Chrome just updated *and* direct egress is blocked), `create_driver()` raises with a recovery hint — run with direct egress or put a matching chromedriver on PATH. (History: this replaced a hardcoded `C:\chromedriver\chromedriver.exe` + `--port=9515`, adopted to dodge a download crash that was actually caused by a stray `HTTP_PROXY` env var, not the network/port/certs.)
- The app is Windows-only in practice: window embedding, the single-instance mutex, and error MessageBoxes all go through `ctypes.windll` (gracefully degrading to no-ops only in `win_window.py`).

## Architecture

Three layers, strictly separated:

**`src/ui/` — Flet desktop UI (MVC).**
- `controller.py` is a thin coordinator delegating to `SettingsController` and `WorkerManager`. It also holds the TYPE 2 **handoff** driver (`_handoff_dm`): when a run ends in the action-required state, the still-alive `DriverManager` is captured here so it survives the worker, and is closed cleanly (`driver.quit()`) when the operator clicks "done" or starts the next run (otherwise the old browser/driver would leak into the next run).
- `worker_manager.py` picks the processor based on `config.TYPE` and runs it on a daemon `threading.Thread`.
- `worker.py` defines a custom signal/slot system (`_Emitter`/`WorkerSignals` with `.connect`/`.emit`) — **not** Qt despite the naming. Channels include `browser_ready` (Chrome's HWND, for embedding) and `browser_detached` (run ended action-required; UI keeps Chrome embedded). The worker runs the processor, catches `StopRequestedException` as a *successful* stop, and **always** emits `finished` in a `finally` block — closing the driver there unless the processor set `keep_browser_open` (only `CandidateProcessor` does) *and* the run completed cleanly.
- `main_window.py` — the window runs locked full-screen (not resizable, always maximized, custom title bar) so the embedded Chrome panel can never shrink below Lightning's ~1024px desktop breakpoint. It creates/tears down the `BrowserOverlay` (`attach_browser` / `enter_browser_handoff`) and on app close force-kills the embedded browser's process tree — keyed off `verified_chrome_pid()` only, never a raw HWND.
- UI updates from the worker thread are marshaled back onto Flet's event loop via `page.run_task(...)` in `controller.py`.
- `main.py` — single-instance guard via a named Win32 mutex (a second launch shows a MessageBox and exits; this replaced an old startup sweep that killed every chromedriver on the machine). `_FeedStream` tees stdout/stderr into the in-app activity feed.

**`src/automation/` — Selenium engine.**
- `processors/` — one class per process `TYPE`, all extending `BaseProcessor`:
  - `LoginProcessor` (TYPE=1): per row, dispatches on the Excel `סוג` (type) column (values 1–6) to combinations of `perform_search` / `create_actions` / `create_report`.
  - `CandidateProcessor` (TYPE=2): adds candidates to a service schedule by ID number.
  - `AttendanceProcessor` (TYPE=3): fills an attendance matrix via the **Aura API** instead of per-row UI clicking.
- `BaseProcessor` owns the shared driver lifecycle (`_setup_driver`), the full login+TOTP flow (`_login`), tabular-input loading + empty guard (`_load_rows`, taking a `TabularSource`), and the cooperative stop mechanism.
- `actions.py` — the low-level Selenium step functions used by `LoginProcessor`.
- `selectors.py` — all XPath selectors, centralized.
- `api_client.py` — `SalesforceApiClient` posts Aura RPC requests via `driver.execute_async_script` (`fetch` from the page context, reusing the logged-in session/token) and strips the Salesforce JSON-hijack prefix (`*/`, `while(1);`) from responses. Used by TYPE 3.
- `data_source.py` — the input seam (epic #14, issue #15): abstract `TabularSource` (TYPE 1/2 → list of Hebrew-keyed row dicts) and `MatrixSource` (TYPE 3 → attendance dict). The only implementations are the in-memory `MemoryTabularSource` / `MemoryMatrixSource`, built by the entry grid — **the grid is the only input source; there is no Excel-file import**. Processors depend on these interfaces only.
- `driver_manager.py` — acquires the driver via **Selenium Manager** (`webdriver.Chrome(service=Service())`, no path/port), strips proxy env vars first (`setup_proxy()` — load-bearing, see the class docstring for the stray-`HTTP_PROXY` saga). chromedriver's own output is sent to `DEVNULL` — **never a PIPE**: an undrained pipe fills, blocks chromedriver, and hangs every WebDriver call (and the cooperative Stop with it). The chromedriver process is taken from `driver.service.process` so the embedding can still find Chrome by its PID and `close_driver()` can terminate it. Chrome launches **off-screen** at a fixed desktop-class size (1600×1000, `--force-device-scale-factor=1` — see win_window notes) so it never flashes on the desktop before the UI embeds it; once the window materialises, its HWND is reframed as an owned tool-window immediately (kills the taskbar flash) and reported via `on_browser_ready`. `detach` is deliberately **OFF** (it leaked a browser per run); the TYPE 2 action-required state instead keeps the whole driver alive and the controller closes it later. `close_driver()` bounds `driver.quit()` with a 5s watchdog thread (a wedged chromedriver must not freeze the UI thread), then terminates the chromedriver process — which also closes Chrome on every exit path. **Security note:** during a TYPE 2 handoff the embedded window keeps a *logged-in Salesforce session* open; the operator is expected to finish the manual step and close it from the panel.
- `win_window.py` — Win32 toolkit for the **embedded browser panel** (issue #19): the *real* Chrome window is shown over the app's panel rectangle as a frameless **owned** top-level window (`GWLP_HWNDPARENT` owner + `WS_POPUP`/`WS_EX_TOOLWINDOW`), with `BrowserOverlay` running a ~100 Hz tracker thread that keeps it glued to the panel (and snaps it back if anything maximizes it). All of it is Windows-only and best-effort — every failure is swallowed so embedding can never break a run; with no embedding the run still works, just unembedded.

**`src/core/` — config, constants, utils, exceptions, logging.**
- `config.py` — singleton `Config` reading `config.ini`; `config_instance` is the global imported everywhere as `parm`. `validate()` returns context-aware missing-field lists keyed off `TYPE` (credentials + URL always; Activity NUMBER/DESCRIPTION for TYPE 1). No input-file path is validated — data comes from the grid.
- Two deliberately separate output channels (issue #12, see `docs/logging-channels.md`): **status** (`status_messages.py` — clean, high-level, Hebrew, for the operator) vs **log** (`logger.py` — technical, English, verbose, for the activity feed/console). `error_messages.humanize_error` maps raw exceptions to an operator-facing (title, hint) pair classified by the stage that failed. Keep new messages on the right channel.

## Critical constraints (do not "clean up" these)

- **Selectors and wait timings are load-bearing.** XPaths in `selectors.py` and the `sleep`/timeout values in `actions.py` are tuned against Salesforce's live DOM and must not be shortened or changed unless the Salesforce UI itself changed. The files carry explicit "do not modify" banners.
- **Clicks use `driver.execute_script("arguments[0].click();", el)`** in many places instead of `.click()` — this is a deliberate workaround for `ElementClickInterceptedException`. Keep it.
- **The stop mechanism is cooperative and interruptible.** Never use bare `time.sleep` or blocking `WebDriverWait`/`find_element` in automation code. Use the wrappers in `src/core/utils.py`:
  - `smart_sleep(duration, check_stop)` instead of `sleep`
  - `interruptible_find_element(...)` / `interruptible_wait(...)` instead of `driver.find_element` / `WebDriverWait`
  - call `verify_running(check_stop)` / `self.check_for_stop()` between steps

  These poll a `threading.Event` and raise `StopRequestedException` so the user's Stop button takes effect mid-flight (including during long waits). Processors thread the stop check through as `check_stop_func=lambda: self.is_stopped`.
- **The owned-overlay embedding has validated invariants** (`win_window.py`, issue #19):
  - Use the **owner** relationship (`GWLP_HWNDPARENT`), never `SetParent`/`WS_CHILD` — true reparenting breaks keyboard input across processes and `AttachThreadInput` doesn't rescue it.
  - Never `SW_HIDE` Chrome while a page may be loading — it stalls the load ("stuck loading"). To get it out of the way, **park it off-screen** (the tracker does this when `rect_provider()` returns None).
  - Don't maximize the automation Chrome and keep `--force-device-scale-factor=1`: OS display scaling shrinks the CSS viewport below Lightning's ~1024px desktop breakpoint, breaking the tuned selectors with `ElementClickIntercepted`.
  - Any force-kill must key off `BrowserOverlay.verified_chrome_pid()` (live-window + same-PID identity guard), never a stored HWND — Windows recycles handles and you'd kill a stranger's process.

## Input data

Input is entered in the in-app grid (`src/ui/data_grid.py`) — typed directly or **smart-pasted** from a copied Excel/Sheets cell range (`paste_parser.py`, issue #17). There is **no Excel-file import**: the grid is the only input source. The grid is drafted to `draft.json` (issue #18) and restored on launch. Rows reach the processors as Hebrew-keyed dicts accessed by literal string: `row['תעודות זהות']` (ID number), `row['סוג']` (type), `row['תאריך']` (date). The `סוג` value drives which automation steps run in `LoginProcessor`.

## Process types (`config.TYPE`)

Every TYPE takes its input from the entry grid (`worker_manager.start(source)` guards on a non-empty in-memory source).

- `1` → `LoginProcessor` (also requires Activity NUMBER + DESCRIPTION in settings)
- `2` → `CandidateProcessor`
- `3` → `AttendanceProcessor`: fills an attendance matrix via the Aura API (compare/upsert modes — see `docs/type3-attendance-modes.md`).

UI styling conventions live in `DESIGN_SYSTEM.md` (consult it before touching theme/layout).
