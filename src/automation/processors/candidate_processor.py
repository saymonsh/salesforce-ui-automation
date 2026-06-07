import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from src.automation.processors.base_processor import BaseProcessor
from src.automation import selectors as S
from src.core.config import config_instance as parm
from src.core.exceptions import StopRequestedException
from src.core.logger import logger
from src.core.status_messages import Status
from src.core.utils import interruptible_find_element


class CandidateProcessor(BaseProcessor):
    def process(self, source):
        # `source` is a TabularSource (issue #15) — Excel or the manual-entry grid.
        rows = self._load_rows(source)
        if rows is None:
            return

        self.check_for_stop()

        # Launch Driver & Login
        self._setup_driver()
        self._login(parm.URL)

        self.check_for_stop()
        # Specific long path click from add_candidats.py
        init_btn = interruptible_find_element(self.driver, By.XPATH, S.CANDIDATE_INITIAL_BUTTON, check_stop_func=lambda: self.is_stopped)
        init_btn.click()

        total = len(rows)
        if self.signals:
            self.signals.started.emit(total)

        for index, row in enumerate(rows):
            self.check_for_stop()

            id_number = row['תעודות זהות']

            id_number = int(id_number)
            n = index + 1
            logger.set_context(stage="candidate", row=n)
            self.update_ui(status=Status.t2_processing(n, total, id_number))
            logger.info(f"adding candidate id {id_number}", stage="candidate", row=n)
            self.check_for_stop()
            
            pyperclip.copy(str(id_number))
            search = interruptible_find_element(self.driver, By.XPATH, S.CANDIDATE_ID_INPUT, check_stop_func=lambda: self.is_stopped)
            search.click()
            self.check_for_stop()
            
            search.clear()
            search.send_keys(Keys.CONTROL, 'v')
            self.check_for_stop()
            
            add_id = interruptible_find_element(self.driver, By.XPATH,
                                         S.CANDIDATE_CHECKBOX_TEMPLATE.format(id_number=id_number), check_stop_func=lambda: self.is_stopped)
            self.driver.execute_script("arguments[0].click();", add_id)
            
            self.check_for_stop()
            clear = interruptible_find_element(self.driver, By.XPATH, S.CANDIDATE_ID_INPUT, check_stop_func=lambda: self.is_stopped)
            clear.clear()
            
            if self.signals:
                self.signals.item_processed.emit()

        logger.reset_context()
        # End state requires a manual "next" in Salesforce → warning, not success.
        # Keep Chrome open so the operator can complete that step (the worker
        # detaches instead of closing the driver when this flag is set).
        self.keep_browser_open = True
        self.update_ui(status=Status.t2_done(total), level="warning")