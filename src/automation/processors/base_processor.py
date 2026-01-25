from abc import ABC, abstractmethod

class BaseProcessor(ABC):
    def __init__(self, signals=None):
        self.signals = signals

    @abstractmethod
    def process(self, *args, **kwargs):
        pass

    def update_ui(self, status=None, progress=None, error=None):
        if self.signals:
            if status:
                self.signals.status.emit(status)
            if progress is not None:
                self.signals.progress.emit(progress)
            if error:
                 # Assuming error is boolean or message, but if it implies failure we might want to signal finished(False, status)
                 # But keeping strictly to update_ui behavior which just updated text/progress
                 pass
