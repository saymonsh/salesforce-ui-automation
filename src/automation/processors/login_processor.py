import pandas as pd
import pyotp
from selenium.webdriver.common.by import By
from src.automation.driver_manager import DriverManager
from src.automation.processors.base_processor import BaseProcessor
from src.automation import actions
from src.core.config import config_instance as parm
from src.core.exceptions import StopException
from src.core.utils import verify_running

class LoginProcessor(BaseProcessor):
    def __init__(self, signals=None):
        super().__init__(signals)
        self.driver = None
        self.chromedriver_process = None

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
             # Logic from login.py login_and_process
            excel_data = pd.read_excel(uploaded_file_path)

            if len(excel_data) == 0:
                print("Excel file is empty.")
                self.update_ui(status="File is empty", error=True)
                return
            
            verify_running(lambda: self.is_stopped)

            # Launch Driver
            self.chromedriver_process = DriverManager.launch_chromedriver()
            
            verify_running(lambda: self.is_stopped)
            self.driver = DriverManager.create_driver()

            # Login Logic
            secret_key = parm.SECRET_KEY
            totp = pyotp.TOTP(secret_key)

            verify_running(lambda: self.is_stopped)
            self.driver.get("https://welfareministry.lightning.force.com/lightning/page/home")
            
            verify_running(lambda: self.is_stopped)
            self.driver.implicitly_wait(30)
            self.driver.maximize_window()

            verify_running(lambda: self.is_stopped)
            username = self.driver.find_element(By.XPATH, "//input[@id='username']")
            username.send_keys(parm.USER_NAME)
            
            verify_running(lambda: self.is_stopped)
            password = self.driver.find_element(By.XPATH, "//input[@id='password']")
            password.send_keys(parm.PASSWORD)
            
            verify_running(lambda: self.is_stopped)
            self.driver.find_element(By.XPATH, "//input[@id='Login']").click()
            
            verify_running(lambda: self.is_stopped)
            tc = self.driver.find_element(By.XPATH, "//input[@id='tc']")
            tc.send_keys(totp.now())
            
            verify_running(lambda: self.is_stopped)
            self.driver.find_element(By.XPATH, "//input[@id='save']").click()

            counter = 1
            print(f"Total rows in Excel: {len(excel_data)}")

            for index, row in excel_data.iterrows():
                verify_running(lambda: self.is_stopped)

                id_number = row['תעודות זהות']
                typer = row['סוג']
                date = row['תאריך']
                
                # Update Progress
                percent = int((counter / len(excel_data)) * 100)
                print(f"{counter}/{len(excel_data)} - {percent}%")
                self.update_ui(progress=percent)
                
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
                    # Original code had exit(400) for type 1, but others just print.
                    # Preserving strict behavior:
                    if row['סוג'] == 1:
                        raise Exception("Critical Failure: Type 1 processing failed.")

                counter += 1

        except StopException:
            print("Process stopped by user (StopException caught).")
            self.update_ui(status="Execution Stopped")
            if self.driver:
                try:
                    print("Forcing driver close due to stop...")
                    self.driver.quit()
                except Exception as e:
                    print(f"Error during forced driver close: {e}")
                finally:
                    self.driver = None

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            
            # Reset UI state (handled by controller via callback usually, but here just status)


            if self.chromedriver_process:
                self.chromedriver_process.terminate()
            print("chrome driver has been terminated")
            
            # Final status update if stopped
            if self.is_stopped:
                self.update_ui(status="Execution Stopped")
