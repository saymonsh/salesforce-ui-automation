from src.core.utils import smart_sleep, verify_running
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

    driver.implicitly_wait(30)

    smart_sleep(5, check_stop)
    
    # Search Button
    search = driver.find_element(By.XPATH, S.SEARCH_BUTTON)
    search.click()

    verify_running(check_stop)

    # Input Search
    search_key = driver.find_element(By.XPATH, S.SEARCH_INPUT)
    search_key.send_keys(f"{id_number}")
    search_key.send_keys(Keys.ENTER)

    verify_running(check_stop)
    smart_sleep(3, check_stop)

    # Wait for element and click
    pa = WebDriverWait(driver, 30).until(ec.element_to_be_clickable((By.XPATH, S.SEARCH_RESULT_LINK)))
    pa.click()

    smart_sleep(3, check_stop)




def create_actions(driver, typer, check_stop=None):
    verify_running(check_stop)
    driver.refresh()
    verify_running(check_stop)
    smart_sleep(5, check_stop)

    create_action = WebDriverWait(driver, 30).until(
        ec.element_to_be_clickable((By.XPATH, S.CREATE_ACTION_BUTTON)))
    create_action.click()

    verify_running(check_stop)

    if typer == 1 or typer == 2:
        select_action1 = driver.find_element(By.XPATH, S.SELECT_ACTION_ROW8)
        select_action1.click()
    
    # Using config value for ACT_NU
    select_action2_element = driver.find_element(By.XPATH,
                                                 S.SELECT_ACTION_ACT_NU_TEMPLATE.format(act_nu=parm.ACT_NU))
    driver.execute_script("arguments[0].scrollIntoView(true);", select_action2_element)
    select_action2_element.click()

    verify_running(check_stop)

    # Next
    click_next = driver.find_element(By.XPATH, S.NEXT_BUTTON)
    click_next.click()

    verify_running(check_stop)

    save = driver.find_element(By.XPATH, S.SAVE_BUTTON)
    driver.execute_script("arguments[0].click();", save)

    smart_sleep(3, check_stop)




def create_report(driver, date, typer, check_stop=None):
    verify_running(check_stop)
    driver.refresh()
    verify_running(check_stop)

    report_button = driver.find_element(By.XPATH, S.REPORT_BUTTON)
    report_button.click()

    verify_running(check_stop)

    if typer != 6:
        action_report_element = driver.find_element(By.XPATH, S.REPORT_ACTION_ROW8)
        action_report_element.click()
    elif typer == 6:
        # Using config value for ACT_NU
        action_report_element = driver.find_element(By.XPATH,
                                                    S.REPORT_ACTION_ACT_NU_TEMPLATE.format(act_nu=parm.ACT_NU))
        driver.execute_script("arguments[0].click();", action_report_element)

    next_to_report = driver.find_element(By.XPATH, S.NEXT_BUTTON)
    next_to_report.click()

    verify_running(check_stop)

    action_date = driver.find_element(By.XPATH, S.ACTION_DATE_INPUT)
    action_date.send_keys(date)

    action_Status = driver.find_element(By.XPATH, S.ACTION_STATUS_SELECT)
    action_Status.click()

    verify_running(check_stop)

    # Using config value for ACT_DESCRIPTION
    activity_description = driver.find_element(By.XPATH, S.ACTIVITY_DESCRIPTION_TEXTAREA)
    activity_description.send_keys(parm.ACT_DESCRIPTION)

    communicationType = driver.find_element(By.XPATH, S.COMMUNICATION_TYPE_SELECT)
    communicationType.click()

    next_to_save_report = driver.find_element(By.XPATH, S.NEXT_BUTTON)
    next_to_save_report.click()
    
    verify_running(check_stop)

    save_report = driver.find_element(By.XPATH, S.FINISH_BUTTON)
    save_report.click()

    smart_sleep(3, check_stop)
