import re
from src.core.utils import smart_sleep, verify_running
from src.automation.processors.base_processor import BaseProcessor
from src.automation.excel_parser import ExcelParser
from src.automation.api_client import SalesforceApiClient
from src.core.config import config_instance as parm
from src.core.exceptions import StopException

class AttendanceProcessor(BaseProcessor):
    def process(self, uploaded_file_path):
        try:
            # 1. Extract Parent Record ID from URL
            url = parm.URL
            match = re.search(r'(?:recordId=|Pa_Service_Schedule__c/)([a-zA-Z0-9]+)', url)
            if not match:
                raise ValueError("לא ניתן לחלץ recordId מתוך הכתובת המוגדרת ב-config.ini")
            parent_record_id = match.group(1)

            # 2. Parse Excel
            self.update_ui(status="קורא קובץ אקסל...")
            excel_data = ExcelParser.parse_attendance_matrix(uploaded_file_path)
            
            verify_running(lambda: self.is_stopped)

            # 3. Setup Driver & Login
            self.update_ui(status="מתחבר לסיילספורס...")
            self._setup_driver()
            self._login(parm.URL)
            
            verify_running(lambda: self.is_stopped)
            
            # Allow page to load so $A is available
            smart_sleep(5, lambda: self.is_stopped)
            
            api_client = SalesforceApiClient(self.driver)

            # 4. Get Participants
            self.update_ui(status="שולף רשימת משתתפים...")
            sfdc_participants_map = api_client.get_participants(parent_record_id)
            
            verify_running(lambda: self.is_stopped)
            
            # Check for missing IDs
            missing_ids = []
            valid_participants = []
            
            for p in excel_data['participants']:
                id_num = p['id_number']
                if id_num not in sfdc_participants_map:
                    missing_ids.append(id_num)
                else:
                    valid_participants.append(p)
                    
            if not valid_participants:
                raise ValueError("אף אחד ממספרי הזהות באקסל לא נמצא ברשימת המשתתפים בפעילות.")

            # 5. Process Dates
            total_dates = len(excel_data['dates'])
            sessions_created = 0
            
            for idx, date_str in enumerate(excel_data['dates']):
                verify_running(lambda: self.is_stopped)
                
                percent = int((idx / total_dates) * 100)
                self.update_ui(progress=percent, status=f"מעבד תאריך {date_str}...")
                
                # Create UTC datetime strings. Salesforce expects YYYY-MM-DDTHH:MM:SS.000Z
                start_dt_utc = f"{date_str}T{excel_data['start_time']}:00.000Z"
                end_dt_utc = f"{date_str}T{excel_data['end_time']}:00.000Z"
                
                # Create Session
                session_id = api_client.create_session(parent_record_id, start_dt_utc, end_dt_utc)
                sessions_created += 1
                
                verify_running(lambda: self.is_stopped)
                
                # Build Attendance Payload
                records_to_update = []
                for p in valid_participants:
                    id_num = p['id_number']
                    sfdc_id = sfdc_participants_map[id_num]
                    status = p['attendance'].get(date_str, "לא נוכח")
                    
                    record = {
                        "Id": sfdc_id,
                        "Pa_Action_Status__c": status
                    }
                    if status == "לא נוכח":
                        record["Pa_No_Action_Reason__c"] = "אחר"
                        
                    records_to_update.append(record)
                    
                # Report Attendance
                api_client.report_attendance(records_to_update)
                
            self.update_ui(progress=100, status="התהליך הסתיים בהצלחה!")
            
            # Prepare summary report
            report = f"נוצרו ודווחו בהצלחה {sessions_created} מפגשים.\n"
            if missing_ids:
                report += f"\nשים לב: {len(missing_ids)} מספרי זהות מהאקסל לא אותרו בסיילספורס ולא עודכנו:\n"
                report += ", ".join(missing_ids)
                
            return report

        except StopException:
            print("Attendance Processor: Stopped by user.")
            self.update_ui(status="הפעולה הופסקה על ידי המשתמש.")
            self._force_close_driver()
            return "הפעולה הופסקה על ידי המשתמש."

        except Exception as e:
            if self.is_stopped:
                print("Attendance Processor: Stopped by user (via generic exception).")
                self.update_ui(status="הפעולה הופסקה על ידי המשתמש.")
                return "הפעולה הופסקה על ידי המשתמש."
            else:
                import traceback
                traceback.print_exc()
                self.update_ui(status="אירעה שגיאה", error=True)
                return f"אירעה שגיאה בתהליך:\n{str(e)}"

        finally:
            self._cleanup_driver()
            self.update_ui(status="אנא לחץ 'הבא' להמשך")
