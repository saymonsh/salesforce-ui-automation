import sys

# The app's OS window title. Shared so the automation layer can locate the host
# window (to embed Chrome as an owned overlay, issue #19) without importing the UI.
APP_WINDOW_TITLE = "כיוון — Salesforce Automation"

# Dry-run / demo mode: launched as `python -m src.main --dry_run`. Drives the full
# UI lifecycle (progress, status, embedded panel) with NO Selenium, chromedriver,
# Salesforce, or login — a throwaway window is embedded in place of Chrome so the
# owned-overlay panel is exercised too. Single source of truth; read at import.
DRY_RUN = "--dry_run" in sys.argv
