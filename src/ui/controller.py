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
            on_finished=self.on_worker_finished,
            on_progress=self.update_progress,
            on_status=self.update_status,
        )
        self.worker_manager.start_thread()

    def update_progress(self, value):
        self.main_view.set_progress(value)

    def update_status(self, status):
        if status != "Done":
            self.main_view.set_status(status)

    def on_worker_finished(self, success, message):
        self.worker_manager.set_idle_ui()

        if not success:
            self.main_view.set_status(f"Error: {message}")
        else:
            self.main_view.set_status(message)

        self.worker_manager.cleanup()
