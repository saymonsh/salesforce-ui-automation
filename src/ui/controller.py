import os

from src.core.config import config_instance as parm
from src.ui.settings_controller import SettingsController
from src.ui.worker_manager import WorkerManager


class Controller:
    """
    Main application controller. Acts as a thin coordinator that delegates to:
    - SettingsController: settings dialog management
    - WorkerManager: worker lifecycle
    """

    def __init__(self, page, main_view):
        self.page = page
        self.main_view = main_view
        self.uploaded_file_path = parm.UPLOADED_FILE_PATH or None

        self.settings_controller = SettingsController(page, main_view)
        self.worker_manager = WorkerManager(main_view)

        self._attach_events()
        self._init_ui_state()
        
        # State tracking for progress
        self.total_items = 0
        self.current_item = 0

    def _init_ui_state(self):
        if self.uploaded_file_path:
            self.main_view.set_selected_file(self.uploaded_file_path)

    def _attach_events(self):
        self.main_view.bind_actions(
            on_browse=self.on_browse_button_click,
            on_run=self.on_run_click,
            on_stop=self.on_stop_click,
            on_settings=self.on_setting_click,
            on_help=self.on_help_click,
        )

    def on_help_click(self, _event=None):
        self.main_view.show_help_dialog()

    def on_browse_button_click(self, file_path):
        self.uploaded_file_path = file_path
        self.main_view.set_status(f"נבחר קובץ: {os.path.basename(file_path)}")

    def on_setting_click(self, _event=None):
        self.settings_controller.open_settings()
        self.uploaded_file_path = parm.UPLOADED_FILE_PATH or None

    def on_stop_click(self, _event=None):
        self.worker_manager.stop()

    def on_run_click(self, _event=None):
        started = self.worker_manager.start(self.uploaded_file_path)
        if not started:
            return

        self.worker_manager.connect_signals(
            on_started=self.on_worker_started,
            on_finished=self.on_worker_finished,
            on_item_processed=self.on_item_processed,
            on_status=self.update_status,
        )
        self.worker_manager.start_thread()

    def on_worker_started(self, total_items: int):
        self.total_items = max(1, total_items)
        self.current_item = 0
        if self.page:
            self.page.run_task(self._safe_worker_started, total_items)
        else:
            self.main_view.set_progress(0.0)
            self.main_view.set_status(f"Starting process... ({total_items} items)")

    async def _safe_worker_started(self, total_items):
        self.main_view.set_progress(0.0, 0, self.total_items)
        self.main_view.set_status(f"Starting process... ({total_items} items)")

    def on_item_processed(self):
        self.current_item += 1
        percentage = self.current_item / self.total_items
        if self.page:
            self.page.run_task(self._safe_update_progress, percentage, self.current_item, self.total_items)
        else:
            self.main_view.set_progress(percentage, self.current_item, self.total_items)

    async def _safe_update_progress(self, percentage, current, total):
        self.main_view.set_progress(percentage, current, total)

    def update_status(self, status):
        if status != "Done":
            if self.page:
                self.page.run_task(self._safe_update_status, status)
            else:
                self.main_view.set_status(status)

    async def _safe_update_status(self, status):
        self.main_view.set_status(status)

    def on_worker_finished(self, success, message):
        if self.page:
            self.page.run_task(self._safe_worker_finished, success, message)
        else:
            # Handle synchronously if page is missing or tests
            self.worker_manager.set_idle_ui()
            if not success:
                self.main_view.set_status(f"Error: {message}", level="error")
                self.main_view.set_progress(0.0)
            elif message != "Execution Stopped":
                self.main_view.set_progress(1.0)
                self.main_view.set_status(message, level="success")
            else:
                self.main_view.set_status(message)
            self.worker_manager.cleanup()

    async def _safe_worker_finished(self, success, message):
        self.worker_manager.set_idle_ui()

        if not success:
            self.main_view.set_status(f"Error: {message}", level="error")
            self.main_view.set_progress(0.0)  # Reset or error state
        elif message != "Execution Stopped":
            self.main_view.set_progress(1.0)  # Force 100% completion
            self.main_view.set_status(message, level="success")
        else:
            self.main_view.set_status(message)

        self.worker_manager.cleanup()

