from src.core.exceptions import StopRequestedException
from src.core.config import config_instance as parm
from src.core.error_messages import humanize_error
from src.core.logger import logger
from src.automation.driver_manager import DriverManager

class _Emitter:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)

class WorkerSignals:
    """
    Defines the channels available from a running worker thread.

    Supported channels:
    started
        int: total_items
    finished
        bool: success status
        str: message/result
    item_processed
        (no args)
    status
        str: high-level Hebrew milestone for the operator (status field)
        str | None: optional severity level ("success" / "warning" / "error")
    log
        str: formatted debug line for the activity feed/console
        str: severity ("DEBUG" / "INFO" / "WARNING" / "ERROR")

    The status and log channels are deliberately separate (issue #12): status
    is clean, high-level, Hebrew; log is technical, English, verbose.
    """
    def __init__(self):
        self.started = _Emitter()
        self.finished = _Emitter()
        self.item_processed = _Emitter()
        self.status = _Emitter()
        self.log = _Emitter()


class AutomationWorker:
    """
    Worker class to execute automation tasks in a separate thread.
    """
    def __init__(self, processor_class, *args, **kwargs):
        self.processor_class = processor_class
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.processor = None
        self.driver_manager = DriverManager()

    def stop(self):
        if self.processor:
            self.processor.stop()

    def run(self):
        success = False
        message = "Unknown error"
        detail = ""  # actionable hint shown in the failure dialog (errors only)
        # Route the central logger's debug output into the activity feed for the
        # duration of this run, and honour the configured verbosity.
        logger.set_verbose(getattr(parm, "DEBUG_LOGGING", False))
        logger.bind(lambda line, level: self.signals.log.emit(line, level))
        try:
            self.processor = self.processor_class(signals=self.signals, driver_manager=self.driver_manager)

            self.processor.process(*self.args, **self.kwargs)

            success = True
            message = "Done"

        except StopRequestedException:
            success = True
            message = "Execution Stopped"
            logger.info("run stopped by user", stage="run")

        except Exception as e:
            success = False
            # Map the raw exception to an operator-facing (title, hint) — title
            # for the one-line status field, hint for the failure dialog —
            # classified by the stage we failed in. The full technical detail +
            # traceback still goes to the debug channel below.
            message, detail = humanize_error(e, logger.current_stage)
            logger.error(f"run aborted: {e}", stage="run", exc=True)

        finally:
            self.driver_manager.close_driver()
            logger.unbind()
            logger.reset_context()
            # Guarantee of Completion:
            # Emit final resolution state to UI
            self.signals.finished.emit(success, message, detail)
