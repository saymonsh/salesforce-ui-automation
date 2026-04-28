class _Emitter:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self._callbacks):
            callback(*args)


class WorkerSignals:
    """
    Defines the channels available from a running worker thread.

    Supported channels:
    finished
        bool: success status
        str: message/result
    progress
        int: progress value (0-100)
    status
        str: status message
    """

    def __init__(self):
        self.finished = _Emitter()
        self.progress = _Emitter()
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

    def stop(self):
        if self.processor:
            self.processor.stop()

    def run(self):
        try:
            self.processor = self.processor_class(signals=self.signals)
            processor = self.processor
            processor.process(*self.args, **self.kwargs)

            if processor.is_stopped:
                self.signals.finished.emit(True, "Execution Stopped")
            else:
                self.signals.finished.emit(True, "Done")

        except Exception as e:
            self.signals.finished.emit(False, str(e))
