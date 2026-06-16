from src.automation.processors.base_processor import BaseProcessor
from src.automation import actions
from src.core.config import config_instance as parm
from src.core.exceptions import StopRequestedException
from src.core.logger import logger
from src.core.status_messages import Status


class LoginProcessor(BaseProcessor):
    def __init__(self, signals=None, driver_manager=None):
        super().__init__(signals, driver_manager)

    def process(self, source):
        # `source` is a TabularSource (issue #15) — Excel or the manual-entry
        # grid (issue #16); the processor is agnostic to where the rows came from.
        rows = self._load_rows(source)
        if rows is None:
            return

        self.check_for_stop()

        # Launch Driver & Login
        self._setup_driver()
        self._login("https://welfareministry.lightning.force.com/lightning/page/home")

        total = len(rows)
        if self.signals:
            self.signals.started.emit(total)

        # Rows that errored mid-run (any סוג). A single bad ID — e.g. one not found
        # by perform_search — is skipped and recorded here so the run continues to
        # the remaining rows instead of aborting; the completion dialog lists them
        # honestly rather than counting a failed row as "processed". perform_search
        # starts each row with driver.refresh(), so the page self-resets between
        # rows and a mid-row failure doesn't poison the next one.
        failed: list[tuple] = []

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
                logger.error(f"failed for id {id_number}: {e}", stage="run", row=n, exc=True)
                failed.append((id_number, str(e)))

            if self.signals:
                self.signals.item_processed.emit()

        logger.reset_context()
        self.update_ui(status=Status.t1_done(total), level="success")

        # Structured run summary for the completion dialog + persistent card.
        summary = {"success_text": Status.t1_summary(total - len(failed))}
        if failed:
            summary["problems_title"] = Status.failed_rows_title(len(failed))
            summary["problem_ids"] = [str(i) for i, _ in failed]
        return summary
