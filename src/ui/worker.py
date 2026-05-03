import traceback

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
    progress
        int: current_item
        int: total_items
        float: percentage (0.0 to 100.0)
    status
        str: status message
    """
    def __init__(self):
        self.started = _Emitter()
        self.finished = _Emitter()
        self.progress = _Emitter()
        self.status = _Emitter()


class ProgressManager:
    """
    State manager for progress calculation and emission.
    """
    def __init__(self, signals: WorkerSignals):
        self.signals = signals
        self.total = 0
        self.current = 0
        self._is_initialized = False

    def initialize(self, total_items: int):
        self.total = max(1, total_items) # Prevent DivisionByZero
        self.current = 0
        self._is_initialized = True
        self.signals.started.emit(self.total)
        self.emit_progress()

    def advance(self, step: int = 1, status: str = None):
        if not self._is_initialized:
            return
        self.current = min(self.total, self.current + step)
        if status:
            self.signals.status.emit(status)
        self.emit_progress()

    def emit_progress(self):
        percentage = (self.current / self.total) * 100.0 if self.total > 0 else 0.0
        self.signals.progress.emit(self.current, self.total, percentage)
        
    def complete(self):
        """Forces the progress to 100%."""
        if self._is_initialized:
            self.current = self.total
            self.emit_progress()


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

    def stop(self):
        if self.processor:
            self.processor.stop()

    def run(self):
        success = False
        message = "Unknown error"
        try:
            self.processor = self.processor_class(signals=self.signals)
            processor = self.processor
            
            # The processor implementation must call:
            # self.signals.started.emit(total_count) or initialize a ProgressManager
            
            processor.process(*self.args, **self.kwargs)

            if processor.is_stopped:
                success = True
                message = "Execution Stopped"
            else:
                success = True
                message = "Done"

        except Exception as e:
            success = False
            message = str(e)
            traceback.print_exc()

        finally:
            # Guarantee of Completion:
            # Emit final resolution state to UI
            self.signals.finished.emit(success, message)
