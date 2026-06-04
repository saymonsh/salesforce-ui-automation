from src.automation.processors.base_processor import BaseProcessor
from src.automation import actions
from src.automation.data_source import ExcelTabularSource
from src.core.config import config_instance as parm
from src.core.exceptions import StopRequestedException
from src.core.logger import logger
from src.core.status_messages import Status


class LoginProcessor(BaseProcessor):
    def __init__(self, signals=None, driver_manager=None):
        super().__init__(signals, driver_manager)

    def process(self, uploaded_file_path):
        rows = self._load_rows(ExcelTabularSource(uploaded_file_path))
        if rows is None:
            return

        self.check_for_stop()

        # Launch Driver & Login
        self._setup_driver()
        self._login("https://welfareministry.lightning.force.com/lightning/page/home")

        total = len(rows)
        if self.signals:
            self.signals.started.emit(total)

        for index, row in enumerate(rows):
            self.check_for_stop()

            id_number = row['תעודות זהות']
            typer = row['סוג']
            date = row['תאריך']

            n = index + 1
            logger.set_context(stage="run", row=n)
            self.update_ui(status=Status.t1_processing(n, total, id_number, typer))
            logger.info(f"processing id {id_number} (סוג {typer})", stage="run", row=n)

            try:
                check = lambda: self.stop_event.is_set()

                if row['סוג'] == 1:
                    actions.perform_search(self.driver, id_number, check_stop=check)
                    actions.create_actions(self.driver, typer, check_stop=check)
                    actions.create_report(self.driver, date, typer, check_stop=check)
                elif row['סוג'] == 2:
                    actions.perform_search(self.driver, id_number, check_stop=check)
                    actions.create_actions(self.driver, typer, check_stop=check)
                elif row['סוג'] == 3:
                    actions.perform_search(self.driver, id_number, check_stop=check)
                    actions.create_report(self.driver, date, typer, check_stop=check)
                elif row['סוג'] == 4:
                    actions.perform_search(self.driver, id_number, check_stop=check)
                    actions.create_actions(self.driver, typer, check_stop=check)
                    actions.create_report(self.driver, date, typer, check_stop=check)
                elif row['סוג'] == 5:
                    actions.perform_search(self.driver, id_number, check_stop=check)
                    actions.create_actions(self.driver, typer, check_stop=check)
                elif row['סוג'] == 6:
                    actions.perform_search(self.driver, id_number, check_stop=check)
                    actions.create_report(self.driver, date, typer, check_stop=check)
            except StopRequestedException:
                raise # Re-raise to be caught by outer try-except in worker.py
            except Exception as e:
                # Check if stopped - if so, this exception might be due to driver close
                if isinstance(e, StopRequestedException):
                    raise e

                logger.error(f"failed for id {id_number}: {e}", stage="run", row=n, exc=True)
                if row['סוג'] == 1:
                    raise Exception("Critical Failure: Type 1 processing failed.")

            if self.signals:
                self.signals.item_processed.emit()

        logger.reset_context()
        self.update_ui(status=Status.t1_done(total), level="success")
