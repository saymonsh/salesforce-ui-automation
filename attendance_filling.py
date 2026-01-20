import os
import subprocess
from time import sleep
import socket

import pyotp
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, \
    ElementNotInteractableException, WebDriverException, InvalidSessionIdException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

# הנחה שקובץ זה קיים באותה תיקייה ומכיל את הפרמטרים הנדרשים
import parameters as parm


def attendance_filling_process():
    # Remove proxy settings if they interfere with localhost connection to chromedriver
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'

    chromedriver_path = r"C:\chromedriver\chromedriver.exe"  # עדכן נתיב אם נדרש
    service_port = 9515  # Port for chromedriver
    chromedriver_url = f"http://127.0.0.1:{service_port}"

    # Initialize TOTP
    secret_key = parm.SECRET_KEY
    totp = pyotp.TOTP(secret_key)

    # Chrome Options
    chrome_options = Options()
    chrome_options.add_argument("--disable-notifications")
    # chrome_options.add_experimental_option("detach", True) # Not strictly needed for Remote if chromedriver persists

    print("Chrome options set.")

    # Check if chromedriver service is already running on the specified port
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
            sleep(3)  # Give chromedriver time to start

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
            wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='username']"))).send_keys(
                parm.USER_NAME)
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
                except Exception as qe:
                    print(f"Error quitting driver during initial setup failure: {qe}")
            return

    else:  # chromedriver_service_running is True
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
                print("Login page not detected. Assuming already logged in or Salesforce will handle session.")

            if login_needed:
                print("Logging in (in the new tab)...")
                wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='username']"))).send_keys(
                    parm.USER_NAME)
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
            print(f"Failed to connect to or use existing chromedriver on port {service_port}: {e_connect}")
            print("Attempting to stop existing chromedriver processes and start a new one (fallback)...")

            try:
                if os.name == 'nt':
                    kill_result = subprocess.run(["taskkill", "/f", "/im", "chromedriver.exe"], capture_output=True,
                                                 text=True, check=False)
                    print(
                        f"Taskkill chromedriver.exe: stdout='{kill_result.stdout.strip()}', stderr='{kill_result.stderr.strip()}'")
                else:
                    kill_result = subprocess.run(["pkill", "-f", "chromedriver"], capture_output=True, text=True,
                                                 check=False)
                    print(
                        f"pkill chromedriver: stdout='{kill_result.stdout.strip()}', stderr='{kill_result.stderr.strip()}'")
                sleep(2)
            except Exception as e_kill:
                print(f"Exception during attempt to kill chromedriver: {e_kill}")

            print("Starting a new chromedriver instance (fallback)...")
            try:
                creation_flags = 0
                if os.name == 'nt':
                    creation_flags = subprocess.CREATE_NO_WINDOW
                subprocess.Popen([chromedriver_path, f"--port={service_port}"], creationflags=creation_flags)
                sleep(3)

                driver = webdriver.Remote(command_executor=chromedriver_url, options=chrome_options)
                print("Connected to new chromedriver (fallback). Launching browser and logging in.")

                wait_long = WebDriverWait(driver, 30)
                wait_interaction = WebDriverWait(driver, 10)
                wait_option = WebDriverWait(driver, 5)
                wait_for_continue = WebDriverWait(driver, 3600)

                driver.get(parm.URL)
                driver.maximize_window()
                print("Logging in (fallback)...")
                wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='username']"))).send_keys(
                    parm.USER_NAME)
                driver.find_element(By.XPATH, "//input[@id='password']").send_keys(parm.PASSWORD)
                driver.find_element(By.XPATH, "//input[@id='Login']").click()
                wait_long.until(ec.presence_of_element_located((By.XPATH, "//input[@id='tc']"))).send_keys(totp.now())
                driver.find_element(By.XPATH, "//input[@id='save']").click()
                print("Login successful (fallback).")

                start_button_locator = (By.XPATH, "//button[contains(.,'דיווח נוכחות למשתתפים')]")
                wait_long.until(ec.element_to_be_clickable(start_button_locator)).click()
                print("Navigated to attendance page (fallback).")

            except Exception as e_fallback_start:
                print(f"Failed to start and connect during fallback: {e_fallback_start}")
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                return

    if not driver:
        print("Driver initialization failed after all attempts. Exiting script.")
        return

    # --- Main attendance filling logic ---
    try:
        print("Waiting for user to click 'Continue' button (JavaScript injected button)...")
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
            wait_for_continue.until(
                lambda drv: drv.execute_script(
                    "return document.body.getAttribute('data-selenium-continue') === 'true';")
            )
            print("'Continue' button clicked by user.")
            driver.execute_script(
                "var btn = document.getElementById('seleniumContinueButton'); if (btn) { btn.remove(); }")
        except TimeoutException:
            print("Timeout waiting for 'Continue' button click by user. Exiting attendance filling.")
            return

        try:
            first_status_button_in_table = (By.XPATH, "(//tr/td[3]//button[contains(@id, 'combobox-button-')])[1]")
            wait_interaction.until(ec.presence_of_element_located(first_status_button_in_table))
            print("Attendance table content is present.")
        except TimeoutException:
            print("Error: Timeout while waiting for attendance table content after clicking start.")
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
                print("No more attendance comboboxes with 'בחר אפשרות' found. Process likely complete.")
                break

            try:
                button_element = potential_buttons[0]
                button_id = button_element.get_attribute('id')
                print(f"Found button to mark attendance: ID {button_id}")

                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                                          button_element)
                    sleep(0.3)
                except Exception as scroll_err:
                    print(f"Warning: Scrolling error - {scroll_err}")

                button_to_click = wait_interaction.until(ec.element_to_be_clickable(button_locator))
                driver.execute_script("arguments[0].click();", button_to_click)

                dropdown_id = button_to_click.get_attribute('aria-controls')
                if not dropdown_id:
                    print(f"Error: Could not find aria-controls for button {button_id}. Skipping this entry.")
                    print("Critical error: dropdown_id not found. Stopping attendance marking.")
                    break

                option_locator = (By.XPATH,
                                  f"//div[@id='{dropdown_id}']//lightning-base-combobox-item[@role='option' and @data-value='נוכח']")

                present_option = wait_option.until(ec.element_to_be_clickable(option_locator))
                print(f"Found 'נוכח' option for dropdown '{dropdown_id}'. Attempting to click.")

                try:
                    driver.execute_script("arguments[0].click();", present_option)
                    print("Option 'נוכח' clicked (JavaScript).")
                except Exception as js_err:
                    print(f"JavaScript click for 'נוכח' option also failed: {js_err}")
                    raise

                sleep(0.2)
                print("-" * 20)
                counter += 1

            except TimeoutException as e_inner:
                print(
                    f"TimeoutException within attendance marking loop {counter} (button/option not clickable or found): {e_inner}. Stopping.")
                break
            except Exception as e_inner:
                print(
                    f"Unexpected error in attendance marking loop {counter}: {type(e_inner).__name__} - {e_inner}. Stopping.")
                break

        print("Attendance marking processing loop finished.")

    except InvalidSessionIdException as e_session:  # תופס שגיאת סשן לא תקין באופן ספציפי
        print(f"A critical session error occurred: {type(e_session).__name__} - {e_session}")
        print("This often means the browser window was closed or the connection to it was lost.")
        print("Please ensure the browser remains open during script operation, especially during waits for user input.")
        # אין צורך לקרוא ל-driver.quit() כאן, מכיוון שהסשן כבר לא תקין
    except Exception as e_main:  # תופס שגיאות כלליות אחרות
        print(f"An error occurred during the main attendance filling process: {type(e_main).__name__} - {e_main}")

    finally:
        print("Attendance filling process function completed.")
        if driver:
            try:
                current_url = driver.current_url  # נסיון לגשת ל-URL כדי לבדוק אם הסשן עדיין פעיל
                print(f"Current URL at script end: {current_url}")
                print("The browser window will remain open. Chromedriver service should also remain running.")
            except WebDriverException:  # אם הגישה ל-URL נכשלת (למשל, InvalidSessionIdException)
                print("Could not retrieve current URL at script end, session might be invalid.")
                print("The browser window might have been closed or became unresponsive.")
        else:
            print("Driver was not initialized or was lost.")
