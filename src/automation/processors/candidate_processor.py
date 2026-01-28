import pandas as pd
import pyotp
import pyperclip
from time import sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from src.automation.driver_manager import DriverManager
from src.automation.processors.base_processor import BaseProcessor
from src.core.config import config_instance as parm

class CandidateProcessor(BaseProcessor):
    def process(self, uploaded_file_path):
        driver = None
        chromedriver_process = None

        try:
            excel_data = pd.read_excel(uploaded_file_path)

            if len(excel_data) == 0:
                print("Excel file is empty.")
                self.update_ui(status="❌ File is empty", error=True)
                return

            chromedriver_process = DriverManager.launch_chromedriver()
            driver = DriverManager.create_driver()

            secret_key = parm.SECRET_KEY
            totp = pyotp.TOTP(secret_key)

            driver.get(parm.URL)
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
            
            # Specific long path click from add_candidats.py
            driver.find_element(By.XPATH, "/html/body/div[4]/div[2]/div/div[2]/div/div[2]/div/div/div/div/runtime_platform_actions-executor-lwc-screen/c-find-p-es-to-service-schedule-action/lightning-quick-action-panel/div/slot/c-find-p-es-to-service-schedule-container/lightning-card/article/div[2]/slot/lightning-card/article/div[2]/slot/div/lightning-button[1]/button").click()

            counter = 1
            sleep(10)

            print(f"Total rows in Excel: {len(excel_data)}")

            for index, row in excel_data.iterrows():
                if self.is_stopped:
                    print("Candidate Processor: Stopping execution...")
                    self.update_ui(status="🛑 Execution Stopped")
                    break

                id_number = row['תעודות זהות']
                typer = row['סוג'] # Unused in original logic but read

                percent = int((counter / len(excel_data)) * 100)
                print(f"{counter}/{len(excel_data)} - {percent}%")
                self.update_ui(progress=percent)
                
                id_number = int(id_number)
                if self.is_stopped: break
                
                pyperclip.copy(str(id_number))
                search = driver.find_element(By.XPATH, "//input[@placeholder='תעודת זהות']")
                search.click()
                if self.is_stopped: break
                
                search.clear()
                search.send_keys(Keys.CONTROL, 'v')
                if self.is_stopped: break
                
                add_id = driver.find_element(By.XPATH,
                                             f".//td[number()= '{id_number}']/preceding-sibling::td//input[@type = 'checkbox']")
                driver.execute_script("arguments[0].click();", add_id)
                
                if self.is_stopped: break
                clear = driver.find_element(By.XPATH, "//input[@placeholder='תעודת זהות']")
                clear.clear()
                counter += 1
                # ui["Button_run"].text = 'run' # Original had this, probably to reset text if it changed?
                
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            self.update_ui(status="❌ Error occurred", error=True)

        finally:
            # if self.ui_callback:
            #      self.ui_callback(status="Done")

            if chromedriver_process:
                chromedriver_process.terminate()
            print("chrome driver has been terminated")
