from src.core.utils import smart_sleep, verify_running
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from src.core.config import config_instance as parm # Alias to match original usage style if preferred, or just use config object

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
    search = driver.find_element(By.XPATH,
                                 "//button[@class='slds-button slds-button_neutral search-button slds-truncate']")
    search.click()

    verify_running(check_stop)

    # Input Search
    search_key = driver.find_element(By.XPATH, "//input[@placeholder='חיפוש...']")
    search_key.send_keys(f"{id_number}")
    search_key.send_keys(Keys.ENTER)

    verify_running(check_stop)
    smart_sleep(3, check_stop)

    # Wait for element and click
    pa = WebDriverWait(driver, 30).until(ec.element_to_be_clickable((By.XPATH,
                                                                     "//*[@id='brandBand_2']/div/div/div[2]/div/div["
                                                                     "2]/div/div/div/div[3]/div/div/div/div/div["
                                                                     "2]/div[1]/div[2]/div/div/div/div[2]/div[2]/div["
                                                                     "1]/div/div/table/tbody/tr/th/span/a")))
    pa.click()

    smart_sleep(3, check_stop)




def create_actions(driver, typer, check_stop=None):
    verify_running(check_stop)
    driver.refresh()
    verify_running(check_stop)
    smart_sleep(5, check_stop)

    create_action = WebDriverWait(driver, 30).until(
        ec.element_to_be_clickable((By.XPATH, "//button[contains(.,'יצירת פעילויות/תוכנית אישית')]")))
    create_action.click()

    verify_running(check_stop)

    if typer == 1 or typer == 2:
        select_action1 = driver.find_element(By.XPATH, ".//tr[8]/td/lightning-primitive-cell-checkbox/span/label/span")
        select_action1.click()
    
    # Using config value for ACT_NU
    select_action2_element = driver.find_element(By.XPATH,
                                                 f".//tr[{parm.ACT_NU}]/td/lightning-primitive-cell-checkbox/span"
                                                 f"/label/span")
    driver.execute_script("arguments[0].scrollIntoView(true);", select_action2_element)
    select_action2_element.click()

    verify_running(check_stop)

    # Next
    click_next = driver.find_element(By.XPATH, "//button[contains(.,'הבא')]")
    click_next.click()

    verify_running(check_stop)

    save = driver.find_element(By.XPATH, "//button[text()='שמירה']")
    driver.execute_script("arguments[0].click();", save)

    smart_sleep(3, check_stop)




def create_report(driver, date, typer, check_stop=None):
    verify_running(check_stop)
    driver.refresh()
    verify_running(check_stop)

    report_button = driver.find_element(By.XPATH,
                                        "//li[@data-target-selection-name='sfdc:QuickAction.Pa_Program_Engagements__c"
                                        ".Pa_Create_Service_Delivery']//button[text()='דיווח שירות']")
    report_button.click()

    verify_running(check_stop)

    if typer != 6:
        action_report_element = driver.find_element(By.XPATH,
                                                    ".//tr[8]/td[2]/lightning-primitive-cell-checkbox/span/label/span")
        action_report_element.click()
    elif typer == 6:
        # Using config value for ACT_NU
        action_report_element = driver.find_element(By.XPATH,
                                                    f".//tr[{parm.ACT_NU}]/td[2]/lightning-primitive-cell-checkbox/span/label/span")
        driver.execute_script("arguments[0].click();", action_report_element)

    next_to_report = driver.find_element(By.XPATH, "//button[contains(.,'הבא')]")
    next_to_report.click()

    verify_running(check_stop)

    action_date = driver.find_element(By.XPATH, "//input[@name='Action_Date_1']")
    action_date.send_keys(date)

    action_Status = driver.find_element(By.XPATH, "//select[@name='Action_Status_1']/option[2]")
    action_Status.click()

    verify_running(check_stop)

    # Using config value for ACT_DESCRIPTION
    activity_description = driver.find_element(By.XPATH,
                                               "//span[text()='תיאור פעילות']/ancestor::flowruntime-lwc-field//textarea")
    activity_description.send_keys(parm.ACT_DESCRIPTION)

    communicationType = driver.find_element(By.XPATH, "//select[@name='CommunicationType']/option[text()='פגישה']")
    communicationType.click()

    next_to_save_report = driver.find_element(By.XPATH, "//button[contains(.,'הבא')]")
    next_to_save_report.click()
    
    verify_running(check_stop)

    save_report = driver.find_element(By.XPATH, "//button[contains(.,'סיים')]")
    save_report.click()

    smart_sleep(3, check_stop)


