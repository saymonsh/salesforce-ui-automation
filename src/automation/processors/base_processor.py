from abc import ABC, abstractmethod

class BaseProcessor(ABC):
    def __init__(self, ui_callback=None):
        self.ui_callback = ui_callback

    @abstractmethod
    def process(self, *args, **kwargs):
        pass

    def update_ui(self, status=None, progress=None, error=None):
        if self.ui_callback:
            self.ui_callback(status=status, progress=progress, error=error)
