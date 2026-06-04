import re
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from src.core.utils import smart_sleep, verify_running
from src.automation.processors.base_processor import BaseProcessor
from src.automation.excel_parser import ExcelParser
from src.automation.api_client import SalesforceApiClient
from src.core.config import config_instance as parm
from src.core.exceptions import StopRequestedException

# Excel times are entered in Israel local time; Salesforce datetime fields expect UTC.
_IL_TZ = ZoneInfo("Asia/Jerusalem")
_UTC_TZ = ZoneInfo("UTC")


def _to_utc_iso(date_str, time_str):
    """Combine an Excel date (YYYY-MM-DD) + time (HH:MM) interpreted as Israel local
    time and return the UTC instant as Salesforce's YYYY-MM-DDTHH:MM:SS.000Z string.
    Uses the Asia/Jerusalem zone so DST (IDT/IST) is handled automatically."""
    local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=_IL_TZ)
    return local.astimezone(_UTC_TZ).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class AttendanceProcessor(BaseProcessor):
    def _human_pause(self, min_seconds=1.5, max_seconds=4.0):
        """Sleep a random, human-like interval between Aura API calls so the traffic
        pattern doesn't look like rapid-fire automation. Uses smart_sleep so the pause
        stays interruptible by the stop button."""
        delay = random.uniform(min_seconds, max_seconds)
        smart_sleep(delay, lambda: self.is_stopped)

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
            
            # --- XHR/Fetch Sniffer Injection ---
            # Using CDP to inject script before any page loads, so we can intercept 
            # and steal the aura.token and aura.context from Salesforce's own background requests.
            sniffer_script = """
            if (!window.__auraSnifferInjected) {
                window.__sniffedAuraToken = "";
                window.__sniffedAuraContext = "";
                var origSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.send = function(data) {
                    try {
                        if (data && typeof data === 'string') {
                            var mToken = data.match(/aura\\.token=([^&]+)/);
                            if (mToken) window.__sniffedAuraToken = decodeURIComponent(mToken[1]);
                            var mContext = data.match(/aura\\.context=([^&]+)/);
                            if (mContext && mContext[1].length > 10) window.__sniffedAuraContext = decodeURIComponent(mContext[1]);
                        }
                    } catch(e) {}
                    return origSend.apply(this, arguments);
                };
                var origFetch = window.fetch;
                window.fetch = function() {
                    try {
                        var body = arguments[1] ? arguments[1].body : null;
                        if (body && typeof body === 'string') {
                            var mToken = body.match(/aura\\.token=([^&]+)/);
                            if (mToken) window.__sniffedAuraToken = decodeURIComponent(mToken[1]);
                            var mContext = body.match(/aura\\.context=([^&]+)/);
                            if (mContext && mContext[1].length > 10) window.__sniffedAuraContext = decodeURIComponent(mContext[1]);
                        }
                    } catch(e) {}
                    return origFetch.apply(this, arguments);
                };
                window.__auraSnifferInjected = true;
            }
            """
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': sniffer_script})
            # ------------------------------------

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

                # Convert Israel-local Excel times to the UTC strings Salesforce expects.
                start_dt_utc = _to_utc_iso(date_str, excel_data['start_time'])
                end_dt_utc = _to_utc_iso(date_str, excel_data['end_time'])

                # 1. Create the session (Pa_Service_Session__c).
                # Human-like pause (mimics filling the "New Session" dialog).
                self.update_ui(status=f"יוצר מפגש לתאריך {date_str}...")
                self._human_pause(2.0, 4.5)
                session_id = api_client.create_session(parent_record_id, start_dt_utc, end_dt_utc)
                sessions_created += 1

                verify_running(lambda: self.is_stopped)

                # 2. Run the Pa_Create_Service_Delivery flow. This is what actually
                #    creates the per-participant Service Delivery records (they are NOT
                #    auto-created on session insert). The flow returns the created
                #    records and a serialized state we must echo back to finish it.
                # Human-like pause (mimics clicking the "Create Service Delivery" action).
                self.update_ui(status="יוצר רשומות נוכחות...")
                self._human_pause(1.5, 3.5)
                serialized_state, delivery_records = api_client.start_create_sd_flow(session_id)

                verify_running(lambda: self.is_stopped)

                # Map participant -> service-delivery id from the flow's created records.
                service_deliveries_map = {}
                for rec in delivery_records:
                    participant_id = rec.get('Pa_Service_Participant__c')
                    if participant_id:
                        service_deliveries_map[participant_id] = rec.get('Id')

                # 3. Build Attendance Payload
                records_to_update = []
                for p in valid_participants:
                    id_num = p['id_number']
                    sfdc_id = sfdc_participants_map[id_num]

                    if sfdc_id not in service_deliveries_map:
                        print(f"Warning: No Service Delivery found for participant {id_num} ({sfdc_id}) in session {session_id}")
                        continue

                    delivery_id = service_deliveries_map[sfdc_id]
                    status = p['attendance'].get(date_str, "לא נוכח")

                    record = {
                        "Id": delivery_id,
                        "Pa_Action_Status__c": status
                    }
                    if status == "לא נוכח":
                        record["Pa_No_Action_Reason__c"] = "אחר"

                    records_to_update.append(record)

                # 4. Report Attendance (persists the statuses via Apex).
                # Human-like pause that scales with the number of participants being
                # marked (mimics ticking each row in the grid), capped so very large
                # groups don't stall for minutes.
                self.update_ui(status="מדווח נוכחות...")
                n_marked = len(records_to_update)
                pause_min = min(3.0 + n_marked * 0.3, 30.0)
                pause_max = min(6.0 + n_marked * 0.7, 45.0)
                self._human_pause(pause_min, pause_max)
                api_client.report_attendance(records_to_update)

                verify_running(lambda: self.is_stopped)

                # 5. Finish the flow so its post-processing side-effects run
                #    (e.g. activating the related Program Engagement).
                # Human-like pause (mimics clicking "Next"/"Finish").
                self.update_ui(status="מסיים תהליך נוכחות...")
                self._human_pause(1.5, 3.0)
                api_client.finish_create_sd_flow(serialized_state, delivery_records)

            self.update_ui(progress=100, status="התהליך הסתיים בהצלחה!")
            
            # Prepare summary report
            report = f"נוצרו ודווחו בהצלחה {sessions_created} מפגשים.\n"
            if missing_ids:
                report += f"\nשים לב: {len(missing_ids)} מספרי זהות מהאקסל לא אותרו בסיילספורס ולא עודכנו:\n"
                report += ", ".join(missing_ids)
                
            return report

        except StopRequestedException:
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
