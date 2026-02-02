import pandas as pd
import pyotp
import pyperclip
from src.core.utils import smart_sleep, verify_running
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from src.automation.driver_manager import DriverManager
from src.automation.processors.base_processor import BaseProcessor
from src.core.config import config_instance as parm
from src.core.exceptions import StopException

class CandidateProcessor(BaseProcessor):
    def process(self, uploaded_file_path):
        driver = None
        chromedriver_process = None

        try:
            excel_data = pd.read_excel(uploaded_file_path)

            if len(excel_data) == 0:
                print("Excel file is empty.")
                self.update_ui(status="File is empty", error=True)
                return

            verify_running(lambda: self.is_stopped)

            chromedriver_process = DriverManager.launch_chromedriver()
            driver = DriverManager.create_driver()

            verify_running(lambda: self.is_stopped)

            secret_key = parm.SECRET_KEY
            totp = pyotp.TOTP(secret_key)
            
            verify_running(lambda: self.is_stopped)
            driver.get(parm.URL)
            verify_running(lambda: self.is_stopped)
            driver.implicitly_wait(30)
            driver.maximize_window()

            verify_running(lambda: self.is_stopped)
            username = driver.find_element(By.XPATH, "//input[@id='username']")
            username.send_keys(parm.USER_NAME)
            
            verify_running(lambda: self.is_stopped)
            password = driver.find_element(By.XPATH, "//input[@id='password']")
            password.send_keys(parm.PASSWORD)
            
            verify_running(lambda: self.is_stopped)
            driver.find_element(By.XPATH, "//input[@id='Login']").click()
            
            verify_running(lambda: self.is_stopped)
            tc = driver.find_element(By.XPATH, "//input[@id='tc']")
            tc.send_keys(totp.now())
            
            verify_running(lambda: self.is_stopped)
            driver.find_element(By.XPATH, "//input[@id='save']").click()
            
            verify_running(lambda: self.is_stopped)
            # Specific long path click from add_candidats.py
            driver.find_element(By.XPATH, "/html/body/div[4]/div[2]/div/div[2]/div/div[2]/div/div/div/div/runtime_platform_actions-executor-lwc-screen/c-find-p-es-to-service-schedule-action/lightning-quick-action-panel/div/slot/c-find-p-es-to-service-schedule-container/lightning-card/article/div[2]/slot/lightning-card/article/div[2]/slot/div/lightning-button[1]/button").click()

            counter = 1
            smart_sleep(10, lambda: self.is_stopped)

            print(f"Total rows in Excel: {len(excel_data)}")

            for index, row in excel_data.iterrows():
                verify_running(lambda: self.is_stopped)

                id_number = row['תעודות זהות']

                percent = int((counter / len(excel_data)) * 100)
                print(f"{counter}/{len(excel_data)} - {percent}%")
                self.update_ui(progress=percent)
                
                id_number = int(id_number)
                verify_running(lambda: self.is_stopped)
                
                pyperclip.copy(str(id_number))
                search = driver.find_element(By.XPATH, "//input[@placeholder='תעודת זהות']")
                search.click()
                verify_running(lambda: self.is_stopped)
                
                search.clear()
                search.send_keys(Keys.CONTROL, 'v')
                verify_running(lambda: self.is_stopped)
                
                add_id = driver.find_element(By.XPATH,
                                             f".//td[number()= '{id_number}']/preceding-sibling::td//input[@type = 'checkbox']")
                driver.execute_script("arguments[0].click();", add_id)
                
                verify_running(lambda: self.is_stopped)
                clear = driver.find_element(By.XPATH, "//input[@placeholder='תעודת זהות']")
                clear.clear()
                counter += 1
                
        except StopException:
            print("Candidate Processor: Stopped by user.")
            self.update_ui(status="Execution Stopped")
            if driver:
                try:
                    print("Forcing driver close due to stop...")
                    driver.quit()
                except Exception as e:
                    print(f"Error during forced driver close: {e}")
                finally:
                    driver = None

        except Exception as e:
            if self.is_stopped:
                # Fallback if StopException missed or driver closed
                print("Candidate Processor: Stopped by user (via generic exception).")
                self.update_ui(status="Execution Stopped")
            else:
                print(f"An unexpected error occurred: {e}")
                self.update_ui(status="Error occurred", error=True)

        finally:


            if chromedriver_process:
                chromedriver_process.terminate()
            print("chrome driver has been terminated")
