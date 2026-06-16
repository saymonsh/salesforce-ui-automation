"""Dry-run processor (--dry_run, see constants.DRY_RUN).

Drives the full UI signal lifecycle — login milestones, ``started`` denominator,
per-item progress, the type-specific done/handoff end state — with NO Selenium,
chromedriver, Salesforce, or login. The placeholder window is launched and embedded
by :class:`DemoDriverManager` through the same ``_setup_driver`` / ``close_driver``
seams a real run uses, so the owned-overlay panel (issue #19) is exercised too.

It emits the *real* :class:`Status` strings for the configured ``TYPE`` so the
screen looks exactly like a live run. Only the work is faked; every signal the UI
reacts to is genuine.
"""
from src.automation.processors.base_processor import BaseProcessor
from src.core.config import config_instance as parm
from src.core.logger import logger
from src.core.status_messages import Status
from src.core.utils import smart_sleep

# Pacing of the simulated run (seconds). Slow enough to watch the UI react.
_LOGIN_DELAY = 1.2
_ITEM_DELAY = 0.7


class DemoProcessor(BaseProcessor):
    def process(self, source):
        check = lambda: self.is_stopped

        # 1) Bring up + embed the placeholder window (DemoDriverManager), exactly
        #    where a real run launches Chrome.
        self.check_for_stop()
        self._setup_driver()

        # 2) Fake the login milestones for fidelity (same status strings as _login).
        logger.set_context(stage="login")
        self.update_ui(status=Status.LOGGING_IN)
        logger.info("demo: pretending to log in", stage="login")
        smart_sleep(_LOGIN_DELAY, check)
        self.check_for_stop()
        self.update_ui(status=Status.MFA_OK)
        smart_sleep(_LOGIN_DELAY, check)
        logger.set_context(stage="run")

        # 3) Work out the item count from whichever source shape we got, and seed
        #    the progress denominator (the UI divides by this — must be emitted).
        items = self._items(source)
        total = len(items)
        if self.signals:
            self.signals.started.emit(total)

        # 4) Tick through the items, emitting the type-specific status each time.
        for n, item in enumerate(items, start=1):
            self.check_for_stop()
            self.update_ui(status=self._processing_status(n, total, item))
            logger.info(f"demo: item {n}/{total}", stage="run", row=n)
            smart_sleep(_ITEM_DELAY, check)
            if self.signals:
                self.signals.item_processed.emit()

        logger.reset_context()
        return self._finish(total)

    # ------------------------------------------------------------------ helpers
    def _items(self, source):
        """The list of units to tick through, from either source shape."""
        if hasattr(source, "rows"):
            return source.rows()
        if hasattr(source, "matrix"):
            return list((source.matrix() or {}).get("dates") or [])
        return []

    def _processing_status(self, n, total, item):
        t = parm.TYPE
        if t == 1:
            row = item if isinstance(item, dict) else {}
            return Status.t1_processing(n, total, row.get("תעודות זהות", n), row.get("סוג", ""))
        if t == 2:
            row = item if isinstance(item, dict) else {}
            return Status.t2_processing(n, total, row.get("תעודות זהות", n))
        if t == 3:
            return Status.t3_processing(str(item), n, total)
        return f"מעבד {n} מתוך {total}"

    def _finish(self, total):
        """Reproduce the real end state for the configured type."""
        t = parm.TYPE
        if t == 2:
            # TYPE 2 ends 'action required': keep the (placeholder) window open and
            # embedded so the handoff panel + its close button are exercised. The
            # worker emits browser_detached; the controller holds DemoDriverManager
            # and closes it (→ window killed) on the panel's "done" button.
            self.keep_browser_open = True
            self.update_ui(status=Status.t2_done(total), level="warning")
            return None
        if t == 3:
            self.update_ui(status=Status.t3_done(total), level="success")
            # Surface the persistent summary card too (no unmatched IDs in a demo).
            return {"sessions_created": total, "missing_ids": []}
        self.update_ui(status=Status.t1_done(total), level="success")
        return None


# --------------------------------------------------------------------- self-check
# Runnable demo/self-check (no framework): `python -m src.automation.processors.demo_processor`.
# Verifies the signal protocol — started(N) then N×item_processed then a done
# status — without launching any real window (the driver_manager is stubbed).
if __name__ == "__main__":
    from src.automation.data_source import MemoryTabularSource

    class _Rec:
        def __init__(self):
            self.calls = []
        def emit(self, *a):
            self.calls.append(a)

    class _Signals:
        def __init__(self):
            self.started = _Rec()
            self.item_processed = _Rec()
            self.status = _Rec()

    class _StubDM:
        driver = None
        on_browser_ready = None
        check_stop = None
        def launch_chromedriver(self): pass
        def create_driver(self): pass
        def close_driver(self): pass

    parm.TYPE = 1  # force a known type for the assertions
    sig = _Signals()
    src = MemoryTabularSource([{"תעודות זהות": "111", "סוג": 1},
                               {"תעודות זהות": "222", "סוג": 1}])
    DemoProcessor(signals=sig, driver_manager=_StubDM()).process(src)

    assert sig.started.calls == [(2,)], sig.started.calls
    assert len(sig.item_processed.calls) == 2, sig.item_processed.calls
    assert any("הסתיים" in c[0] for c in sig.status.calls), sig.status.calls
    print("OK — started(2), 2×item_processed, done status emitted")
