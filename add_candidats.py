import os
import subprocess
from time import sleep

import pandas as pd
import pyotp
import pyperclip
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
import parameters as parm

def add_candidats_process(uploaded_file_path, ui):
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'

    chromedriver_path = r"C:\chromedriver\chromedriver.exe"
    chromedriver_process = subprocess.Popen([chromedriver_path, "--port=9515"])
    sleep(2)

    excel_data = pd.read_excel(uploaded_file_path)

    if len(excel_data) == 0:
        print("Excel file is empty.")
        ui["status"].text = "❌ File is empty"
        ui["run"].is_visible = True
        ui["Progressbar"].is_visible = False
        return

    # יצירת מפתח חד־פעמי
    secret_key = parm.SECRET_KEY
    totp = pyotp.TOTP(secret_key)
    # הגדרת אפשרויות הדפדפן
    chrome_options = Options()
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-cookies")
    print("Chrome options set.")
    chromedriver_url = "http://127.0.0.1:9515"  # Adjust port if needed
    driver = webdriver.Remote(
        command_executor=chromedriver_url,
        options=chrome_options
    )
    try:
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
        driver.find_element(By.XPATH, "/html/body/div[4]/div[2]/div/div[2]/div/div[2]/div/div/div/div/runtime_platform_actions-executor-lwc-screen/c-find-p-es-to-service-schedule-action/lightning-quick-action-panel/div/slot/c-find-p-es-to-service-schedule-container/lightning-card/article/div[2]/slot/lightning-card/article/div[2]/slot/div/lightning-button[1]/button").click()


        counter = 1
        sleep(10)

        print(f"Total rows in Excel: {len(excel_data)}")

        for index, row in excel_data.iterrows():
            id_number = row['תעודות זהות']
            typer = row['סוג']
            
            # חישוב אחוזים
            percent = int((counter / len(excel_data)) * 100)
            print(f"{counter}/{len(excel_data)} - {percent}%")
            ui["Progressbar"].value = percent
            
            id_number = int(id_number)
            id_number = int(id_number)
            pyperclip.copy(str(id_number))
            search = driver.find_element(By.XPATH, "//input[@placeholder='תעודת זהות']")
            search.click()
            search.clear()
            search.send_keys(Keys.CONTROL, 'v')
            add_id = driver.find_element(By.XPATH,
                                         f".//td[number()= '{id_number}']/preceding-sibling::td//input[@type = 'checkbox']")
            driver.execute_script("arguments[0].click();", add_id)
            clear = driver.find_element(By.XPATH, "//input[@placeholder='תעודת זהות']")
            clear.clear()
            counter += 1
            ui["run"].text = 'run'


    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        ui["status"].text = "❌ Error occurred"

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        
        ui["run"].is_visible = True
        ui["Progressbar"].is_visible = False
        
        if 'chromedriver_process' in locals():
            chromedriver_process.terminate()
        print("chrome driver has been terminated")
