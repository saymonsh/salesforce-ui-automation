from src.automation.processors.base_processor import BaseProcessor
from src.automation import actions
from src.core.config import config_instance as parm
from src.core.exceptions import StopException
from src.core.utils import verify_running


class LoginProcessor(BaseProcessor):
    def __init__(self, signals=None):
        super().__init__(signals)

    def stop(self):
        """
        Signals the processor to stop execution and forcefully closes the driver
        to interrupt any blocking waits.
        """
        super().stop()
        print("LoginProcessor.stop() called - Attempting to force close driver")

        # Force close driver to break blocking waits
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"Error closing driver during stop: {e}")
            finally:
                self.driver = None

    def process(self, uploaded_file_path):
        self.driver = None
        self.chromedriver_process = None

        try:
            excel_data = self._read_excel(uploaded_file_path)
            if excel_data is None:
                return

            verify_running(lambda: self.is_stopped)

            # Launch Driver & Login
            self._setup_driver()
            self._login("https://welfareministry.lightning.force.com/lightning/page/home")

            print(f"Total rows in Excel: {len(excel_data)}")
            if self.progress_manager:
                self.progress_manager.initialize(len(excel_data))

            for index, row in excel_data.iterrows():
                verify_running(lambda: self.is_stopped)

                id_number = row['תעודות זהות']
                typer = row['סוג']
                date = row['תאריך']
                
                try:
                    check = lambda: self.is_stopped
                    # check is passed to actions, but verify_running is preferred if we call it here.
                    # actions likely raise StopException now if check returns true inside them (via smart_sleep or explicit verify)
                    
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
                except StopException:
                    raise # Re-raise to be caught by outer try-except
                except Exception as e:
                    # Check if stopped - if so, this exception might be due to driver close
                    if isinstance(e, StopException):
                        raise e
                        
                    print(f"תקלה במספר זהות: {id_number}, {str(e)}")
                    if row['סוג'] == 1:
                        raise Exception("Critical Failure: Type 1 processing failed.")

                if self.progress_manager:
                    self.progress_manager.advance(1)

        except StopException:
            print("Process stopped by user (StopException caught).")
            self.update_ui(status="Execution Stopped")
            self._force_close_driver()

        finally:
            self._cleanup_driver()
            
            # Final status update if stopped
            if self.is_stopped:
                self.update_ui(status="Execution Stopped")
