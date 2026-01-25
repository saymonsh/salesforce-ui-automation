import os
import subprocess
import socket
import pyotp
from time import sleep
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, InvalidSessionIdException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait
from src.automation.processors.base_processor import BaseProcessor
from src.core.config import config_instance as parm

class AttendanceProcessor(BaseProcessor):
    def process(self):
        # Remove proxy settings
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        os.environ['NO_PROXY'] = '127.0.0.1,localhost'

        chromedriver_path = r"C:\chromedriver\chromedriver.exe"
        service_port = 9515
        chromedriver_url = f"http://127.0.0.1:{service_port}"

        secret_key = parm.SECRET_KEY
        totp = pyotp.TOTP(secret_key)

        chrome_options = Options()
        chrome_options.add_argument("--disable-notifications")
        print("Chrome options set.")

        chromedriver_service_running = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', service_port)) == 0:
                    chromedriver_service_running = True
                    print(f"Chromedriver service appears to be running on port {service_port}.")
        except Exception as e:
            print(f"Error checking port {service_port}: {e}")

        driver = None
        wait_long = None
        wait_interaction = None
        wait_option = None
        wait_for_continue = None

        if not chromedriver_service_running:
            print(f"Chromedriver service not found on port {service_port}. Starting a new chromedriver instance...")
            try:
                creation_flags = 0
                if os.name == 'nt':
                     creation_flags = subprocess.CREATE_NO_WINDOW
                
                subprocess.Popen([chromedriver_path, f"--port={service_port}"], creationflags=creation_flags)
                sleep(3)

                print(f"Attempting to connect to newly started chromedriver on port {service_port}.")
                driver = webdriver.Remote(command_executor=chromedriver_url, options=chrome_options)
                print("Connected to new chromedriver. Launching browser and logging in for the first time.")

                wait_long = WebDriverWait(driver, 30)
                wait_interaction = WebDriverWait(driver, 10)
                wait_option = WebDriverWait(driver, 5)
                wait_for_continue = WebDriverWait(driver, 3600)

                driver.get(parm.URL)
                driver.maximize_window()

                print("Logging in...")
                wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='username']"))).send_keys(parm.USER_NAME)
                driver.find_element(By.XPATH, "//input[@id='password']").send_keys(parm.PASSWORD)
                driver.find_element(By.XPATH, "//input[@id='Login']").click()
                wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='tc']"))).send_keys(totp.now())
                driver.find_element(By.XPATH, "//input[@id='save']").click()
                print("Login successful.")

                start_button_locator = (By.XPATH, "//button[contains(.,'דיווח נוכחות למשתתפים')]")
                wait_long.until(ec.element_to_be_clickable(start_button_locator)).click()
                print("Navigated to attendance page.")

            except Exception as e:
                print(f"Failed to start and connect to new chromedriver or initial login: {e}")
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                return
        else:
             # chromedriver_service_running is True
            print(f"Attempting to connect to existing chromedriver service on port {service_port}.")
            try:
                driver = webdriver.Remote(command_executor=chromedriver_url, options=chrome_options)
                print("Successfully connected to existing chromedriver service.")

                wait_long = WebDriverWait(driver, 30)
                wait_interaction = WebDriverWait(driver, 10)
                wait_option = WebDriverWait(driver, 5)
                wait_for_continue = WebDriverWait(driver, 3600)

                print("Opening a new tab for the script's operations.")
                original_handles = set(driver.window_handles)
                driver.execute_script("window.open('about:blank', '_blank');")

                WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > len(original_handles))
                new_tab_handle = list(set(driver.window_handles) - original_handles)[0]
                driver.switch_to.window(new_tab_handle)

                print(f"Switched to new tab. Navigating to URL: {parm.URL}")
                driver.get(parm.URL)

                login_needed = False
                try:
                    print("Checking if login is required in the new tab...")
                    WebDriverWait(driver, 7).until(ec.presence_of_element_located((By.XPATH, "//input[@id='username']")))
                    login_needed = True
                    print("Login page detected. Login is required.")
                except TimeoutException:
                    print("Login page not detected. Assuming already logged in.")

                if login_needed:
                    print("Logging in (in the new tab)...")
                    wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='username']"))).send_keys(parm.USER_NAME)
                    driver.find_element(By.XPATH, "//input[@id='password']").send_keys(parm.PASSWORD)
                    driver.find_element(By.XPATH, "//input[@id='Login']").click()
                    wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='tc']"))).send_keys(totp.now())
                    driver.find_element(By.XPATH, "//input[@id='save']").click()
                    print("Login successful (in the new tab).")

                print("Ensuring navigation to the attendance page/component...")
                start_button_locator = (By.XPATH, "//button[contains(.,'דיווח נוכחות למשתתפים')]")
                wait_long.until(ec.element_to_be_clickable(start_button_locator)).click()
                print("Navigated to attendance page/component (in the new tab).")

            except WebDriverException as e_connect:
                print(f"Failed to connect to existing chromedriver: {e_connect}. Fallback needed.")
                # Skipping fallback implementation for brevity in this refactor unless critical, 
                # but original code had massive fallback logic. 
                # I should probably include it if I want to be 100% safe, but it duplicates the "not running" logic.
                # I will create a recursive call or just simpler error message for now as a Refactoring decision 
                # to reduce code duplication, OR strictly copy if space permits.
                # Given strict constraints, I'll copy the fallback to be safe.
                
                print("Closing existing processes and restarting...")
                try:
                    if os.name == 'nt':
                        subprocess.run(["taskkill", "/f", "/im", "chromedriver.exe"], capture_output=True, check=False)
                    else:
                        subprocess.run(["pkill", "-f", "chromedriver"], capture_output=True, check=False)
                    sleep(2)
                except Exception:
                    pass

                # Retry start - simpler inline version
                try:
                    creation_flags = 0
                    if os.name == 'nt': creation_flags = subprocess.CREATE_NO_WINDOW
                    subprocess.Popen([chromedriver_path, f"--port={service_port}"], creationflags=creation_flags)
                    sleep(3)
                    driver = webdriver.Remote(command_executor=chromedriver_url, options=chrome_options)
                    wait_long = WebDriverWait(driver, 30)
                    wait_interaction = WebDriverWait(driver, 10)
                    wait_option = WebDriverWait(driver, 5)
                    wait_for_continue = WebDriverWait(driver, 3600)
                    driver.get(parm.URL)
                    driver.maximize_window()
                    wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='username']"))).send_keys(parm.USER_NAME)
                    driver.find_element(By.XPATH, "//input[@id='password']").send_keys(parm.PASSWORD)
                    driver.find_element(By.XPATH, "//input[@id='Login']").click()
                    wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='tc']"))).send_keys(totp.now())
                    driver.find_element(By.XPATH, "//input[@id='save']").click()
                    start_button_locator = (By.XPATH, "//button[contains(.,'דיווח נוכחות למשתתפים')]")
                    wait_long.until(ec.element_to_be_clickable(start_button_locator)).click()
                except Exception as e_fallback:
                    print(f"Fallback failed: {e_fallback}")
                    return

        if not driver:
            return

        # Main Logic
        try:
            print("Waiting for user to click 'Continue' button...")
            js_create_button = """
            var btn = document.createElement('button'); btn.id = 'seleniumContinueButton'; btn.textContent = 'המשך';
            btn.style.position = 'fixed'; btn.style.top = '20px'; btn.style.left = '50%';
            btn.style.transform = 'translateX(-50%)'; btn.style.padding = '12px 24px';
            btn.style.backgroundColor = '#4CAF50'; btn.style.color = 'white'; btn.style.border = 'none';
            btn.style.borderRadius = '8px'; btn.style.cursor = 'pointer'; btn.style.zIndex = '9999';
            btn.style.fontSize = '16px'; btn.style.fontWeight = 'bold';
            btn.style.boxShadow = '0 4px 8px rgba(0,0,0,0.2)';
            btn.onmouseover = function() { btn.style.backgroundColor = '#45a049'; };
            btn.onmouseout = function() { btn.style.backgroundColor = '#4CAF50'; };
            btn.onclick = function() { document.body.setAttribute('data-selenium-continue', 'true'); };
            document.body.appendChild(btn); document.body.setAttribute('data-selenium-continue', 'false');
            """
            driver.execute_script(js_create_button)

            try:
                wait_for_continue.until(lambda drv: drv.execute_script("return document.body.getAttribute('data-selenium-continue') === 'true';"))
                driver.execute_script("var btn = document.getElementById('seleniumContinueButton'); if (btn) { btn.remove(); }")
            except TimeoutException:
                print("Timeout waiting for user.")
                return

            try:
                first_status_button_in_table = (By.XPATH, "(//tr/td[3]//button[contains(@id, 'combobox-button-')])[1]")
                wait_interaction.until(ec.presence_of_element_located(first_status_button_in_table))
            except TimeoutException:
                print("Error: Timeout waiting for table.")
                return

            counter = 1
            while True:
                print(f"--- Attendance marking loop {counter}:")
                button_locator = (By.XPATH,
                                  "(//tr[td[3][.//button[contains(@id, 'combobox-button-') and ./span[text()='בחר אפשרות']]]])[1]"
                                  "//td[3]"
                                  "//button[contains(@id, 'combobox-button-') and ./span[text()='בחר אפשרות']]")

                potential_buttons = driver.find_elements(*button_locator)
                if not potential_buttons:
                    print("No more buttons found.")
                    break

                try:
                    button_element = potential_buttons[0]
                    
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", button_element)
                        sleep(0.3)
                    except:
                        pass

                    button_to_click = wait_interaction.until(ec.element_to_be_clickable(button_locator))
                    driver.execute_script("arguments[0].click();", button_to_click)

                    dropdown_id = button_to_click.get_attribute('aria-controls')
                    if not dropdown_id:
                        break

                    option_locator = (By.XPATH, f"//div[@id='{dropdown_id}']//lightning-base-combobox-item[@role='option' and @data-value='נוכח']")
                    
                    present_option = wait_option.until(ec.element_to_be_clickable(option_locator))
                    driver.execute_script("arguments[0].click();", present_option)
                    
                    sleep(0.2)
                    counter += 1

                except TimeoutException:
                    break
                except Exception as e_inner:
                    print(f"Error in loop: {e_inner}")
                    break

        except InvalidSessionIdException as e:
            print(f"Session error: {e}")
        except Exception as e:
            print(f"Main error: {e}")
        finally:
            print("Finished.")
            # if self.ui_callback:
            #     self.ui_callback(status="Done")
            # Do NOT quit driver for AttendanceProcessor as per original logic logic ("The browser window will remain open")
