import pyperclip
from src.core.utils import smart_sleep, verify_running
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from src.automation.processors.base_processor import BaseProcessor
from src.automation import selectors as S
from src.core.config import config_instance as parm
from src.core.exceptions import StopException


class CandidateProcessor(BaseProcessor):
    def process(self, uploaded_file_path):
        try:
            excel_data = self._read_excel(uploaded_file_path)
            if excel_data is None:
                return

            verify_running(lambda: self.is_stopped)

            # Launch Driver & Login
            self._setup_driver()
            self._login(parm.URL)

            verify_running(lambda: self.is_stopped)
            # Specific long path click from add_candidats.py
            self.driver.find_element(By.XPATH, S.CANDIDATE_INITIAL_BUTTON).click()

            print(f"Total rows in Excel: {len(excel_data)}")
            if self.signals:
                self.signals.started.emit(len(excel_data))

            for index, row in excel_data.iterrows():
                verify_running(lambda: self.is_stopped)

                id_number = row['תעודות זהות']
                
                id_number = int(id_number)
                verify_running(lambda: self.is_stopped)
                
                pyperclip.copy(str(id_number))
                search = self.driver.find_element(By.XPATH, S.CANDIDATE_ID_INPUT)
                search.click()
                verify_running(lambda: self.is_stopped)
                
                search.clear()
                search.send_keys(Keys.CONTROL, 'v')
                verify_running(lambda: self.is_stopped)
                
                add_id = self.driver.find_element(By.XPATH,
                                             S.CANDIDATE_CHECKBOX_TEMPLATE.format(id_number=id_number))
                self.driver.execute_script("arguments[0].click();", add_id)
                
                verify_running(lambda: self.is_stopped)
                clear = self.driver.find_element(By.XPATH, S.CANDIDATE_ID_INPUT)
                clear.clear()
                
                if self.signals:
                    self.signals.item_processed.emit()
                
        except StopException:
            print("Candidate Processor: Stopped by user.")
            self.update_ui(status="Execution Stopped")
            self._force_close_driver()

        except Exception as e:
            if self.is_stopped:
                # Fallback if StopException missed or driver closed
                print("Candidate Processor: Stopped by user (via generic exception).")
                self.update_ui(status="Execution Stopped")
            else:
                print(f"An unexpected error occurred: {e}")
                self.update_ui(status="Error occurred", error=True)

        finally:
            self.update_ui(status="Please click 'next' to continue")