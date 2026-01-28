import pandas as pd
import pyotp
from selenium.webdriver.common.by import By
from src.automation.driver_manager import DriverManager
from src.automation.processors.base_processor import BaseProcessor
from src.automation import actions
from src.core.config import config_instance as parm

class LoginProcessor(BaseProcessor):
    def process(self, uploaded_file_path):
        driver = None
        chromedriver_process = None

        try:
             # Logic from login.py login_and_process
            excel_data = pd.read_excel(uploaded_file_path)

            if len(excel_data) == 0:
                print("Excel file is empty.")
                self.update_ui(status="File is empty", error=True)
                return

            # Launch Driver
            chromedriver_process = DriverManager.launch_chromedriver()
            driver = DriverManager.create_driver()

            # Login Logic
            secret_key = parm.SECRET_KEY
            totp = pyotp.TOTP(secret_key)

            driver.get("https://welfareministry.lightning.force.com/lightning/page/home")
            driver.implicitly_wait(30)
            driver.maximize_window()

            username = driver.find_element(By.XPATH, "//input[@id='username']")
            username.send_keys(parm.USER_NAME)
            password = driver.find_element(By.XPATH, "//input[@id='password']")
            password.send_keys(parm.PASSWORD)
            driver.find_element(By.XPATH, "//input[@id='Login']").click()
            tc = driver.find_element(By.XPATH, "//input[@id='tc']")
            tc.send_keys(totp.now())
            driver.find_element(By.XPATH, "//input[@id='save']").click()

            counter = 1
            print(f"Total rows in Excel: {len(excel_data)}")

            for index, row in excel_data.iterrows():
                if self.is_stopped:
                    print("Example Processor: Stopping execution...")
                    self.update_ui(status="🛑 Execution Stopped")
                    break

                id_number = row['תעודות זהות']
                typer = row['סוג']
                date = row['תאריך']
                
                # Update Progress
                percent = int((counter / len(excel_data)) * 100)
                print(f"{counter}/{len(excel_data)} - {percent}%")
                self.update_ui(progress=percent)
                
                try:
                    check = lambda: self.is_stopped
                    
                    if row['סוג'] == 1:
                        if self.is_stopped: break
                        actions.perform_search(driver, id_number, check_stop=check)
                        if self.is_stopped: break
                        actions.create_actions(driver, typer, check_stop=check)
                        if self.is_stopped: break
                        actions.create_report(driver, date, typer, check_stop=check)
                    elif row['סוג'] == 2:
                        if self.is_stopped: break
                        actions.perform_search(driver, id_number, check_stop=check)
                        if self.is_stopped: break
                        actions.create_actions(driver, typer, check_stop=check)
                    elif row['סוג'] == 3:
                        if self.is_stopped: break
                        actions.perform_search(driver, id_number, check_stop=check)
                        if self.is_stopped: break
                        actions.create_report(driver, date, typer, check_stop=check)
                    elif row['סוג'] == 4:
                        if self.is_stopped: break
                        actions.perform_search(driver, id_number, check_stop=check)
                        if self.is_stopped: break
                        actions.create_actions(driver, typer, check_stop=check)
                        if self.is_stopped: break
                        actions.create_report(driver, date, typer, check_stop=check)
                    elif row['סוג'] == 5:
                        if self.is_stopped: break
                        actions.perform_search(driver, id_number, check_stop=check)
                        if self.is_stopped: break
                        actions.create_actions(driver, typer, check_stop=check)
                    elif row['סוג'] == 6:
                        if self.is_stopped: break
                        actions.perform_search(driver, id_number, check_stop=check)
                        if self.is_stopped: break
                        actions.create_report(driver, date, typer, check_stop=check)
                except Exception as e:
                    print(f"תקלה במספר זהות: {id_number}, {str(e)}")
                    # Original code had exit(400) for type 1, but others just print.
                    # Preserving strict behavior:
                    if row['סוג'] == 1:
                        raise Exception("Critical Failure: Type 1 processing failed.")

                counter += 1

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            self.update_ui(status="Error occurred", error=True)

        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
            # Reset UI state (handled by controller via callback usually, but here just status)
            # if self.ui_callback:
            #      # Special signal to controller that we are done
            #      self.ui_callback(status="Done")

            if chromedriver_process:
                chromedriver_process.terminate()
            print("chrome driver has been terminated")
            
            if self.is_stopped:
                self.update_ui(status="stopped")
            # Else "Done" is emitted by worker, but we might want to override or handle here? 
            # Worker emits "Done" if run() completes without exception. 
            # If we break loop, fun returns.
            # We need to ensure Worker knows. But Worker.run() calls self.signals.finished.emit(True, "Done").
            # We can't easily change worker logic from here without return value.
            # But the user asked for *UI Status* to be "Stopped". 
            # If I emit status "Stopped" here, then Worker emits "Done", the UI might overwrite it.
            # I should update Worker logic or BaseProcessor logic.
            # BaseProcessor doesn't control flow.
            # I'll handle this in Worker or return a value?
            # Worker ignores return value.
            # I will modify the Worker to check is_stopped later.
