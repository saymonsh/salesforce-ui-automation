from src.core.utils import smart_sleep, verify_running, interruptible_wait, interruptible_find_element
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from src.core.config import config_instance as parm
from src.automation import selectors as S

# Original logic from actions.py
# STRICTLY NO LOGIC CHANGES ALLOWED FOR SELENIUM PARTS

def perform_search(driver, id_number, check_stop=None):
    verify_running(check_stop)

    driver.refresh()
    verify_running(check_stop)
    smart_sleep(3, check_stop)

    smart_sleep(5, check_stop)
    
    # Search Button
    search = interruptible_find_element(driver, By.XPATH, S.SEARCH_BUTTON, check_stop_func=check_stop)
    search.click()

    verify_running(check_stop)

    # Input Search
    search_key = interruptible_find_element(driver, By.XPATH, S.SEARCH_INPUT, check_stop_func=check_stop)
    search_key.send_keys(f"{id_number}")
    search_key.send_keys(Keys.ENTER)

    verify_running(check_stop)
    smart_sleep(3, check_stop)

    print(f"DEBUG [perform_search]: Sent search. Waiting for search result link... (Timeout: 30s)")
    print(f"DEBUG [perform_search]: Looking for XPath: {S.SEARCH_RESULT_LINK}")
    try:
        # Wait for element and click
        pa = interruptible_wait(
            driver, 
            ec.element_to_be_clickable((By.XPATH, S.SEARCH_RESULT_LINK)),
            timeout=30,
            check_stop_func=check_stop
        )
        print("DEBUG [perform_search]: Element found and clickable. Clicking...")
        pa.click()
        print("DEBUG [perform_search]: Clicked successfully.")
    except Exception as e:
        print(f"DEBUG [perform_search]: Exception occurred while waiting for link: {str(e)}")
        try:
            driver.save_screenshot("debug_search_error.png")
            print("DEBUG [perform_search]: Saved screenshot to debug_search_error.png")
            with open("debug_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("DEBUG [perform_search]: Saved page source to debug_page_source.html")
        except Exception as screenshot_e:
            print(f"DEBUG [perform_search]: Failed to save debug artifacts: {str(screenshot_e)}")
        raise

    smart_sleep(3, check_stop)




def create_actions(driver, typer, check_stop=None):
    verify_running(check_stop)
    driver.refresh()
    verify_running(check_stop)
    smart_sleep(5, check_stop)

    create_action = interruptible_wait(
        driver, 
        ec.element_to_be_clickable((By.XPATH, S.CREATE_ACTION_BUTTON)),
        timeout=30,
        check_stop_func=check_stop
    )
    create_action.click()

    verify_running(check_stop)

    if typer == 1 or typer == 2:
        select_action1 = interruptible_find_element(driver, By.XPATH, S.SELECT_ACTION_ROW8, check_stop_func=check_stop)
        driver.execute_script("arguments[0].click();", select_action1)
    
    # Using config value for ACT_NU
    select_action2_element = interruptible_find_element(driver, By.XPATH,
                                                 S.SELECT_ACTION_ACT_NU_TEMPLATE.format(act_nu=parm.ACT_NU), check_stop_func=check_stop)
    driver.execute_script("arguments[0].scrollIntoView(true);", select_action2_element)
    driver.execute_script("arguments[0].click();", select_action2_element)

    verify_running(check_stop)

    # Next
    click_next = interruptible_find_element(driver, By.XPATH, S.NEXT_BUTTON, check_stop_func=check_stop)
    click_next.click()

    verify_running(check_stop)

    save = interruptible_find_element(driver, By.XPATH, S.SAVE_BUTTON, check_stop_func=check_stop)
    driver.execute_script("arguments[0].click();", save)

    smart_sleep(3, check_stop)




def create_report(driver, date, typer, check_stop=None):
    verify_running(check_stop)
    driver.refresh()
    verify_running(check_stop)

    report_button = interruptible_find_element(driver, By.XPATH, S.REPORT_BUTTON, check_stop_func=check_stop)
    report_button.click()

    verify_running(check_stop)

    if typer != 6:
        action_report_element = interruptible_find_element(driver, By.XPATH, S.REPORT_ACTION_ROW8, check_stop_func=check_stop)
        driver.execute_script("arguments[0].click();", action_report_element)
    elif typer == 6:
        # Using config value for ACT_NU
        action_report_element = interruptible_find_element(driver, By.XPATH,
                                                    S.REPORT_ACTION_ACT_NU_TEMPLATE.format(act_nu=parm.ACT_NU), check_stop_func=check_stop)
        driver.execute_script("arguments[0].click();", action_report_element)

    next_to_report = interruptible_find_element(driver, By.XPATH, S.NEXT_BUTTON, check_stop_func=check_stop)
    next_to_report.click()

    verify_running(check_stop)

    action_date = interruptible_find_element(driver, By.XPATH, S.ACTION_DATE_INPUT, check_stop_func=check_stop)
    action_date.send_keys(date)

    action_Status = interruptible_find_element(driver, By.XPATH, S.ACTION_STATUS_SELECT, check_stop_func=check_stop)
    action_Status.click()

    verify_running(check_stop)

    # Using config value for ACT_DESCRIPTION
    activity_description = interruptible_find_element(driver, By.XPATH, S.ACTIVITY_DESCRIPTION_TEXTAREA, check_stop_func=check_stop)
    activity_description.send_keys(parm.ACT_DESCRIPTION)

    communicationType = interruptible_find_element(driver, By.XPATH, S.COMMUNICATION_TYPE_SELECT, check_stop_func=check_stop)
    communicationType.click()

    next_to_save_report = interruptible_find_element(driver, By.XPATH, S.NEXT_BUTTON, check_stop_func=check_stop)
    next_to_save_report.click()
    
    verify_running(check_stop)

    save_report = interruptible_find_element(driver, By.XPATH, S.FINISH_BUTTON, check_stop_func=check_stop)
    save_report.click()

    smart_sleep(3, check_stop)
