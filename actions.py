from time import sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
import parameters as parm


def perform_search(driver, id_number):
    driver.refresh()
    sleep(3)

    driver.implicitly_wait(30)

    sleep(5)
    # לחיצה על כפתור החיפוש
    search = driver.find_element(By.XPATH,
                                 "//button[@class='slds-button slds-button_neutral search-button slds-truncate']")
    search.click()

    # הזנת מילת החיפוש
    search_key = driver.find_element(By.XPATH, "//input[@placeholder='חיפוש...']")
    search_key.send_keys(f"{id_number}")
    search_key.send_keys(Keys.ENTER)

    sleep(3)

    # המתנה עד שהאלמנט מוצג ואז לחיצה עליו
    pa = WebDriverWait(driver, 30).until(ec.element_to_be_clickable((By.XPATH,
                                                                     "//*[@id='brandBand_2']/div/div/div[2]/div/div["
                                                                     "2]/div/div/div/div[3]/div/div/div/div/div["
                                                                     "2]/div[1]/div[2]/div/div/div/div[2]/div[2]/div["
                                                                     "1]/div/div/table/tbody/tr/th/span/a")))
    pa.click()

    sleep(3)

    pass


def create_actions(driver, typer):
    driver.refresh()
    sleep(5)

    create_action = WebDriverWait(driver, 30).until(
        ec.element_to_be_clickable((By.XPATH, "//button[contains(.,'יצירת פעילויות/תוכנית אישית')]")))
    create_action.click()

    if typer == 1 or typer == 2:
        select_action1 = driver.find_element(By.XPATH, ".//tr[8]/td/lightning-primitive-cell-checkbox/span/label/span")
        select_action1.click()
    select_action2_element = driver.find_element(By.XPATH,
                                                 f".//tr[{parm.ACT_NU}]/td/lightning-primitive-cell-checkbox/span"
                                                 f"/label/span")
    driver.execute_script("arguments[0].scrollIntoView(true);", select_action2_element)
    select_action2_element.click()

    # לחיצה על כפתור הבא
    click_next = driver.find_element(By.XPATH, "//button[contains(.,'הבא')]")
    click_next.click()

    save = driver.find_element(By.XPATH, "//button[text()='שמירה']")
    driver.execute_script("arguments[0].click();", save)

    sleep(3)

    pass


def create_report(driver, date, typer):
    driver.refresh()
    report_button = driver.find_element(By.XPATH,
                                        "//li[@data-target-selection-name='sfdc:QuickAction.Pa_Program_Engagements__c"
                                        ".Pa_Create_Service_Delivery']//button[text()='דיווח שירות']")
    report_button.click()  # לחיצה על הכפתור

    if typer != 6:
        action_report_element = driver.find_element(By.XPATH,
                                                    ".//tr[8]/td[2]/lightning-primitive-cell-checkbox/span/label/span")
        action_report_element.click()
    elif typer == 6:
        action_report_element = driver.find_element(By.XPATH,
                                                    f".//tr[{parm.ACT_NU}]/td[2]/lightning-primitive-cell-checkbox/span/label/span")
        driver.execute_script("arguments[0].click();", action_report_element)

    next_to_report = driver.find_element(By.XPATH, "//button[contains(.,'הבא')]")
    next_to_report.click()

    action_date = driver.find_element(By.XPATH, "//input[@name='Action_Date_1']")
    action_date.send_keys(date)

    action_Status = driver.find_element(By.XPATH, "//select[@name='Action_Status_1']/option[2]")
    action_Status.click()

    activity_description = driver.find_element(By.XPATH,
                                               "//span[text()='תיאור פעילות']/ancestor::flowruntime-lwc-field//textarea")
    activity_description.send_keys(parm.ACT_description)

    communicationType = driver.find_element(By.XPATH, "//select[@name='CommunicationType']/option[text()='פגישה']")
    communicationType.click()

    next_to_save_report = driver.find_element(By.XPATH, "//button[contains(.,'הבא')]")
    next_to_save_report.click()

    save_report = driver.find_element(By.XPATH, "//button[contains(.,'סיים')]")
    save_report.click()

    sleep(3)

    pass
