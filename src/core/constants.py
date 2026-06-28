import sys

from src.core.version import __version__

# The app's OS window title. Shared so the automation layer can locate the host
# window (to embed Chrome as an owned overlay, issue #19) without importing the UI.
APP_WINDOW_TITLE = f"כיוון — Salesforce Automation  v{__version__}"

# Dry-run / demo mode: launched as `python -m src.main --dry_run`. Drives the full
# UI lifecycle (progress, status, embedded panel) with NO Selenium, chromedriver,
# Salesforce, or login — a throwaway window is embedded in place of Chrome so the
# owned-overlay panel is exercised too. Single source of truth; read at import.
DRY_RUN = "--dry_run" in sys.argv

# TYPE 3 (attendance) sub-modes — the value stored in [Salesforce] T3_MODE.
# (There is deliberately no "mode 1": the old blind-create behaviour was removed.)
T3_MODE_COMPARE = "compare"  # read-only diff of the grid vs Salesforce, zero writes
T3_MODE_UPSERT = "upsert"    # create missing sessions + sync attendance to the grid
