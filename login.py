import os
import subprocess
from time import sleep

import pandas as pd
import pyotp
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import parameters as parm
from actions import perform_search, create_actions, create_report


def login_and_process(uploaded_file_path, ui):
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'

    chromedriver_path = r"C:\chromedriver\chromedriver.exe"
    chromedriver_process = subprocess.Popen([chromedriver_path, "--port=9515"])
    sleep(2)

    # שנה את שורת הקריאה לאקסל ל:
    excel_data = pd.read_excel(uploaded_file_path)

    if len(excel_data) == 0:
        print("Excel file is empty.")
        ui["Text_uploadStatus"].text = "❌ File is empty"
        ui["Button_run"].is_visible = True
        ui["Progressbar"].is_visible = False
        ui["Text_running"].is_visible = False
        ui["Rectangle"].is_visible = False
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
    print("Chrome launched.")
    try:
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
            id_number = row['תעודות זהות']
            typer = row['סוג']
            date = row['תאריך']
            
            # חישוב אחוזים
            percent = int((counter / len(excel_data)) * 100)
            print(f"{counter}/{len(excel_data)} - {percent}%")
            ui["Progressbar"].value = percent
            
            if row['סוג'] == 1:  # יצירת הכנת תוכנית אישית + פעילות ודיווח שירות
                try:
                    perform_search(driver, id_number)
                    create_actions(driver, typer)
                    create_report(driver, date, typer)
                except Exception as e:
                    print(f"תקלה במספר זהות: {id_number}, {str(e)}")
                    exit(400)
            elif row['סוג'] == 2:  # יצירת הכנת תוכנית אישית + פעילות ללא דיווח
                try:
                    perform_search(driver, id_number)
                    create_actions(driver, typer)
                except Exception as e:
                    print(f"תקלה במספר זהות: {id_number}, {str(e)}")
            elif row['סוג'] == 3:  # דיווח שירות תוכנית אישית בלבד
                try:
                    perform_search(driver, id_number)
                    create_report(driver, date, typer)
                except Exception as e:
                    print(f"תקלה במספר זהות: {id_number}, {str(e)}")
            elif row['סוג'] == 4:  # יצירת פעילות ודיווח שירות ללא יצירת תוכנית אישית
                try:
                    perform_search(driver, id_number)
                    create_actions(driver, typer)
                    create_report(driver, date, typer)

                except Exception as e:
                    print(f" תקלה במספר זהות: {id_number}")
            elif row['סוג'] == 5:  # יצירת פעילות ללא תוכנית אישית ודיווח שירות
                try:
                    perform_search(driver, id_number)
                    create_actions(driver, typer)

                except Exception as e:
                    print(f" תקלה במספר זהות: {id_number}")
            elif row['סוג'] == 6:  # דיווח שירות על פעילות אחרת
                try:
                    perform_search(driver, id_number)
                    create_report(driver, date, typer)
                except Exception as e:
                    print(f" תקלה במספר זהות: {id_number} - {e}")

            counter += 1

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        ui["Text_uploadStatus"].text = "❌ Error occurred"

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        
        # שחזור כפתור הריצה וטיפול בסרגל ההתקדמות
        ui["Button_run"].is_visible = True
        ui["Progressbar"].is_visible = False
        ui["Text_running"].is_visible = False
        ui["Rectangle"].is_visible = False
        
        if 'chromedriver_process' in locals():
            chromedriver_process.terminate()
        print("chrome driver has been terminated")
