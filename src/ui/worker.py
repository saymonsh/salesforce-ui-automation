import traceback
from src.core.exceptions import StopRequestedException
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
        str: status message
    """
    def __init__(self):
        self.started = _Emitter()
        self.finished = _Emitter()
        self.item_processed = _Emitter()
        self.status = _Emitter()


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
        try:
            self.processor = self.processor_class(signals=self.signals, driver_manager=self.driver_manager)
            
            self.processor.process(*self.args, **self.kwargs)

            success = True
            message = "Done"

        except StopRequestedException:
            success = True
            message = "Execution Stopped"
            print("Worker caught StopRequestedException.")

        except Exception as e:
            success = False
            message = str(e)
            traceback.print_exc()

        finally:
            self.driver_manager.close_driver()
            # Guarantee of Completion:
            # Emit final resolution state to UI
            self.signals.finished.emit(success, message)
