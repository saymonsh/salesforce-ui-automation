# =============================================================================
# UI Selectors Constants
# All XPath/CSS selectors used by the automation layer.
# These values MUST NOT be modified — they are extracted verbatim from the
# original code to preserve exact UI interaction behavior.
# =============================================================================

# ---- Login Page ----
LOGIN_USERNAME_INPUT = "//input[@id='username']"
LOGIN_PASSWORD_INPUT = "//input[@id='password']"
LOGIN_SUBMIT_BUTTON = "//input[@id='Login']"
LOGIN_TOTP_INPUT = "//input[@id='tc']"
LOGIN_TOTP_SAVE = "//input[@id='save']"
# Salesforce's login error banner (e.g. "A security policy at this org is
# preventing you from logging in."). Read only on the failure path to surface
# the real reason a login timed out — never part of the happy path.
LOGIN_ERROR_BANNER = "//div[@id='error']"

# ---- Search Flow (actions.perform_search) ----
SEARCH_BUTTON = "//button[@class='slds-button slds-button_neutral search-button slds-truncate']"
SEARCH_INPUT = "//input[@placeholder='חיפוש...']"
SEARCH_RESULT_LINK = "//div[contains(@class, 'forceSearchResultsGridLVM')]//table/tbody/tr[1]/th//a"

# ---- Create Actions Flow (actions.create_actions) ----
CREATE_ACTION_BUTTON = "//button[contains(.,'יצירת פעילויות/תוכנית אישית')]"
SELECT_ACTION_ROW8 = ".//tr[8]/td/lightning-primitive-cell-checkbox/span/label/span"
# Note: SELECT_ACTION_ACT_NU uses f-string with parm.ACT_NU, template provided:
SELECT_ACTION_ACT_NU_TEMPLATE = ".//tr[{act_nu}]/td/lightning-primitive-cell-checkbox/span/label/span"
NEXT_BUTTON = "//button[contains(.,'הבא')]"
SAVE_BUTTON = "//button[text()='שמירה']"

# ---- Create Report Flow (actions.create_report) ----
REPORT_BUTTON = (
    "//li[@data-target-selection-name='sfdc:QuickAction.Pa_Program_Engagements__c"
    ".Pa_Create_Service_Delivery']//button[text()='דיווח שירות']"
)
REPORT_ACTION_ROW8 = ".//tr[8]/td[2]/lightning-primitive-cell-checkbox/span/label/span"
# Note: REPORT_ACTION_ACT_NU uses f-string with parm.ACT_NU, template provided:
REPORT_ACTION_ACT_NU_TEMPLATE = ".//tr[{act_nu}]/td[2]/lightning-primitive-cell-checkbox/span/label/span"
ACTION_DATE_INPUT = "//input[@name='Action_Date_1']"
ACTION_STATUS_SELECT = "//select[@name='Action_Status_1']/option[2]"
ACTIVITY_DESCRIPTION_TEXTAREA = "//span[text()='תיאור פעילות']/ancestor::flowruntime-lwc-field//textarea"
COMMUNICATION_TYPE_SELECT = "//select[@name='CommunicationType']/option[text()='פגישה']"
FINISH_BUTTON = "//button[contains(.,'סיים')]"

# ---- Candidate Processor ----
CANDIDATE_INITIAL_BUTTON = "//c-find-p-es-to-service-schedule-action//button[@title='next Step']"
CANDIDATE_ID_INPUT = "//input[@placeholder='תעודת זהות']"
# Note: CANDIDATE_CHECKBOX uses f-string with id_number, template provided:
CANDIDATE_CHECKBOX_TEMPLATE = ".//td[number()= '{id_number}']/preceding-sibling::td//input[@type = 'checkbox']"
