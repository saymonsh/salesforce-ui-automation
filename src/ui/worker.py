from PySide6.QtCore import QObject, Signal

class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:
    finished
        bool: success status
        str: message/result
    error
        tuple: (exctype, value, traceback.format_exc() )
    progress
        int: progress value (0-100)
    status
        str: status message
    """
    finished = Signal(bool, str)
    error = Signal(tuple)
    progress = Signal(int)
    status = Signal(str)

class AutomationWorker(QObject):
    """
    Worker class to execute automation tasks in a separate thread.
    """
    def __init__(self, processor_class, *args, **kwargs):
        super().__init__()
        self.processor_class = processor_class
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.processor = None

    def stop(self):
        """Helper to stop the processor."""
        if self.processor:
             self.processor.stop()

    def run(self):
        """
        Initializes the processor and executes the process method.
        """
        try:
            # Initialize processor with signals
            # We pass the signals object so the processor can emit updates directly
            self.processor = self.processor_class(signals=self.signals)
            processor = self.processor
            
            # Execute the process
            # Assuming process() is blocking and runs the automation
            processor.process(*self.args, **self.kwargs)
            
            if processor.is_stopped:
                # "The action was stopped by the user"
                self.signals.finished.emit(True, "Execution Stopped")
            else:
                self.signals.finished.emit(True, "Done")

        except Exception as e:
            # In case of unhandled exception in the processor
            import traceback
            # self.signals.error.emit((type(e), e, traceback.format_exc()))
            self.signals.finished.emit(False, str(e))
        # finally:
        #     self.signals.finished.emit(True, "Process Completed") # Careful about double emit
