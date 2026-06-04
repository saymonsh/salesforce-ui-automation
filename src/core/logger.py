"""Central structured logger for the debug channel (issue #12).

This is the *debug* half of the two-channel split described in
``docs/logging-channels.md``. It replaces the scattered ``print()`` calls in
``src/automation/`` with leveled, timestamped, context-aware lines:

    {timestamp}  {LEVEL}  [{stage} | {context}]  {message}

Each line goes to two places:
- the real console (``sys.__stdout__``), for the developer/ops terminal;
- the activity feed in the UI, via a *sink* the worker binds for the duration
  of a run (``logger.bind`` → ``WorkerSignals.log``).

The *status* channel (high-level Hebrew milestones for the operator) is a
separate thing entirely — see ``src/core/status_messages.py``.

Usage from automation code::

    from src.core.logger import logger
    logger.info("login OK — TOTP accepted", stage="login")
    with logger.context(stage="search", row=12):
        logger.debug("clicking SEARCH_RESULT_LINK (waited 1.2s)")

The logger is a process-global singleton: only one automation worker runs at a
time, so a shared instance with per-run binding is sufficient.
"""
from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from datetime import datetime

# Severity ordering for threshold filtering.
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


class Logger:
    def __init__(self):
        self._sink = None              # callable(line: str, level: str) -> None
        self._verbose = False          # when False, DEBUG lines are suppressed
        self._stage = "-"
        self._ctx: dict[str, object] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ wiring
    def bind(self, sink) -> None:
        """Route formatted lines to ``sink`` (in addition to the console).

        The worker binds this to ``WorkerSignals.log`` for the run's duration.
        """
        self._sink = sink

    def unbind(self) -> None:
        self._sink = None

    def set_verbose(self, verbose: bool) -> None:
        """Toggle DEBUG verbosity. When off, DEBUG lines are dropped entirely."""
        self._verbose = bool(verbose)

    @property
    def current_stage(self) -> str:
        """The persistent stage the run is in (for error classification).

        Reflects the last ``set_context(stage=…)``; transient ``context(...)``
        blocks restore it on exit, so at the point an exception surfaces this is
        the enclosing phase (``login`` / ``run`` / ``aura`` / ``driver`` …).
        """
        return self._stage

    # ----------------------------------------------------------------- context
    def set_context(self, stage: str | None = None, **ctx) -> None:
        if stage is not None:
            self._stage = stage
        for key, value in ctx.items():
            if value is not None:
                self._ctx[key] = value

    def reset_context(self) -> None:
        self._stage = "-"
        self._ctx = {}

    @contextmanager
    def context(self, stage: str | None = None, **ctx):
        """Temporarily set stage/context, restoring the previous state on exit."""
        prev_stage, prev_ctx = self._stage, dict(self._ctx)
        self.set_context(stage, **ctx)
        try:
            yield
        finally:
            self._stage, self._ctx = prev_stage, prev_ctx

    # ------------------------------------------------------------------- emit
    def _context_str(self) -> str:
        if not self._ctx:
            return "-"
        return ", ".join(f"{key} {value}" for key, value in self._ctx.items())

    def _emit(self, level: str, message: str) -> None:
        if level == "DEBUG" and not self._verbose:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        block = f"[{self._stage} | {self._context_str()}]"
        line = f"{ts}  {level:<7}{block:<26}{message}"
        with self._lock:
            # Console copy — write to the *original* stdout so it bypasses the
            # _FeedStream tee (which would otherwise double the line into the
            # feed). __stdout__ is None under a windowless (pythonw) launch.
            stream = sys.__stdout__
            if stream is not None:
                try:
                    stream.write(line + "\n")
                    stream.flush()
                except Exception:
                    pass
            if self._sink is not None:
                try:
                    self._sink(line, level)
                except Exception:
                    pass

    def debug(self, message: str, stage: str | None = None, **ctx) -> None:
        if stage is not None or ctx:
            with self.context(stage, **ctx):
                self._emit("DEBUG", message)
        else:
            self._emit("DEBUG", message)

    def info(self, message: str, stage: str | None = None, **ctx) -> None:
        if stage is not None or ctx:
            with self.context(stage, **ctx):
                self._emit("INFO", message)
        else:
            self._emit("INFO", message)

    def warning(self, message: str, stage: str | None = None, **ctx) -> None:
        if stage is not None or ctx:
            with self.context(stage, **ctx):
                self._emit("WARNING", message)
        else:
            self._emit("WARNING", message)

    def error(self, message: str, stage: str | None = None, exc: bool = False, **ctx) -> None:
        """Log an ERROR. When ``exc=True``, append the current traceback."""
        if exc:
            import traceback
            tb = traceback.format_exc().rstrip()
            if tb and tb != "NoneType: None":
                message = f"{message}\n{tb}"
        if stage is not None or ctx:
            with self.context(stage, **ctx):
                self._emit("ERROR", message)
        else:
            self._emit("ERROR", message)


# Process-global singleton imported across the automation layer.
logger = Logger()
