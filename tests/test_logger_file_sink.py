"""Self-check for the diag debug-file mirror (diag/netfree-machine) — no framework.

    python tests/test_logger_file_sink.py

The reason this branch exists is to get the debug channel OFF a filtered machine
as an on-disk file. The load-bearing invariant: the file mirror is the COMPLETE
record — it captures DEBUG lines even when ``set_verbose(False)`` keeps them out
of the operator's feed/console. If that ever regresses, the pulled-out log would
be silently missing exactly the detail we went to this trouble for.
"""
import os
import tempfile

from src.core.logger import logger


def check_file_captures_suppressed_debug() -> None:
    path = os.path.join(tempfile.mkdtemp(), "debug.log")
    logger.set_verbose(False)        # feed/console quiet — the normal operator state
    logger.bind_file(path)
    try:
        logger.debug("verbose-off debug line", stage="diag")
        logger.info("an info line", stage="diag")
        for h in logger._file_logger.handlers:
            h.flush()
        with open(path, encoding="utf-8") as f:
            body = f.read()
    finally:
        for h in logger._file_logger.handlers:
            h.close()
        logger._file_logger = None   # unbind so the singleton doesn't leak into other tests

    assert "verbose-off debug line" in body, "file must capture DEBUG even when verbose is off"
    assert "an info line" in body, "file must capture INFO"
    assert "diag" in body, "stage/context must be formatted into the line"


def check_rebind_truncates() -> None:
    """Each bind_file (= each launch) must RESET the log, not append. The mirror is
    overwrite-only, so an appending file grows without bound on the filtered
    machine. Guards the RotatingFileHandler 'maxBytes>0 silently forces mode=a'
    trap that made mode='w' a no-op."""
    path = os.path.join(tempfile.mkdtemp(), "debug.log")
    logger.bind_file(path)
    logger.info("first-launch line", stage="diag")
    logger.bind_file(path)               # simulate a second launch
    logger.info("second-launch line", stage="diag")
    try:
        for h in logger._file_logger.handlers:
            h.flush()
        with open(path, encoding="utf-8") as f:
            body = f.read()
    finally:
        for h in logger._file_logger.handlers:
            h.close()
        logger._file_logger = None

    assert "second-launch line" in body, "current launch must be present"
    assert "first-launch line" not in body, "re-bind must truncate, not append (mirror is overwrite-only)"


def main() -> None:
    check_file_captures_suppressed_debug()
    check_rebind_truncates()
    print("OK: debug-file mirror captures the full record and resets per launch")


if __name__ == "__main__":
    main()
