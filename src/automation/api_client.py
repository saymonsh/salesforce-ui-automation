import json

class SalesforceApiClient:
    def __init__(self, driver):
        self.driver = driver

    def _execute_aura_request(self, endpoint, payload):
        # Increased timeout to 30000ms (30s) for script execution
        self.driver.set_script_timeout(30)
        
        script = """
        var callback = arguments[arguments.length - 1];
        var payload = arguments[0];
        var endpoint = arguments[1];
        
        try {
            var fwuid = "";
            var auraToken = "";
            
            if (window.auraConfig) {
                if (window.auraConfig.context) {
                    fwuid = window.auraConfig.context.fwuid || "";
                }
                auraToken = window.auraConfig.token || "";
            }
            
            if (typeof $A !== 'undefined') {
                var ctx = typeof $A.getContext === 'function' ? $A.getContext() : null;
                if (ctx && ctx.fwuid) {
                    fwuid = fwuid || ctx.fwuid;
                }
                try {
                    var t = $A.get("$A.token");
                    if (t) auraToken = auraToken || t;
                } catch(e) {}
            }
            
            var bodyData = new URLSearchParams();
            bodyData.append('message', JSON.stringify(payload));
            if (auraToken) {
                bodyData.append('aura.token', auraToken);
            }
            
            var context = {"mode":"PROD","app":"one:one","pathPrefix":"","fwuid":fwuid};
            bodyData.append('aura.context', JSON.stringify(context));

            var xSfdcLds = '';
            if (payload.actions && payload.actions[0] && payload.actions[0].params && payload.actions[0].params.classname) {
                xSfdcLds = 'ApexActionController.execute:' + payload.actions[0].params.classname + '.' + payload.actions[0].params.method;
            }

            var headers = {
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
            };
            if (xSfdcLds) {
                headers['x-sfdc-lds-endpoints'] = xSfdcLds;
            }

            fetch(endpoint, {
                method: 'POST',
                headers: headers,
                body: bodyData.toString()
            })
            .then(function(response) {
                return response.text();
            })
            .then(function(text) {
                var cleanText = text.trim();
                if (cleanText.indexOf("*/") === 0) {
                    cleanText = cleanText.substring(2).trim();
                } else if (cleanText.indexOf("while(1);") === 0) {
                    cleanText = cleanText.substring(9).trim();
                }
                try {
                    var data = JSON.parse(cleanText);
                    callback({success: true, data: data});
                } catch(err) {
                    callback({success: false, error: err.message + " | Start of response: " + text.substring(0, 50)});
                }
            })
            .catch(function(error) {
                callback({success: false, error: error.message});
            });
        } catch(err) {
            callback({success: false, error: err.toString()});
        }
        """
        result = self.driver.execute_async_script(script, payload, endpoint)
        if not result.get('success'):
            raise Exception(f"API Error: {result.get('error')}")
        return result.get('data')

    def get_participants(self, parent_record_id):
        payload = {
            "actions": [{
                "id": "1;a",
                "descriptor": "aura://RelatedListUiController/ACTION$postRelatedListRecords",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "parentRecordId": parent_record_id,
                    "relatedListId": "Service_Deliveries__r",
                    "listRecordsQuery": {
                        "fields": [
                            "Pa_Service_Participant__c.Id",
                            "Pa_Service_Participant__c.Pa_ID_Number__c"
                        ],
                        "pageSize": 2000,
                        "pageToken": "0"
                    }
                }
            }]
        }
        
        data = self._execute_aura_request('/aura?r=1&aura.RelatedListUi.postRelatedListRecords=1', payload)
        
        mapping = {}
        try:
            records = data['actions'][0]['returnValue']['records']
            for rec in records:
                sfdc_id = rec['id']
                id_num = rec['fields']['Pa_ID_Number__c']['value']
                if id_num:
                    mapping[str(id_num)] = sfdc_id
        except KeyError as e:
            print(f"Error parsing participants response: {e}, Data: {data}")
            
        return mapping

    def create_session(self, parent_record_id, start_dt_utc, end_dt_utc):
        payload = {
            "actions": [{
                "id": "2;a",
                "descriptor": "aura://RecordUiController/ACTION$createRecord",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "recordInput": {
                        "allowSaveOnDuplicate": False,
                        "apiName": "Pa_Service_Session__c",
                        "fields": {
                            "Pa_Service_Schedule__c": parent_record_id,
                            "Pa_Session_Start_DateTime__c": start_dt_utc,
                            "Pa_Session_End_DateTime__c": end_dt_utc
                        }
                    }
                }
            }]
        }
        
        data = self._execute_aura_request('/aura?r=2&aura.RecordUi.createRecord=1', payload)
        try:
            session_id = data['actions'][0]['returnValue']['id']
            return session_id
        except KeyError:
            raise Exception(f"Failed to extract Session ID from createRecord response. Data: {data}")

    def report_attendance(self, records_to_update):
        if not records_to_update:
            return
            
        payload = {
            "actions": [{
                "id": "3;a",
                "descriptor": "aura://ApexActionController/ACTION$execute",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "namespace": "",
                    "classname": "ServiceDeliveryController",
                    "method": "updateServiceDelivery",
                    "params": {
                        "recordsToUpdate": records_to_update,
                        "objectName": ""
                    },
                    "cacheable": False,
                    "isContinuation": False
                }
            }]
        }
        
        data = self._execute_aura_request('/aura?r=3&aura.ApexAction.execute=1', payload)
        try:
            state = data['actions'][0]['state']
            if state != 'SUCCESS':
                # Check for deeper errors
                error_msgs = data['actions'][0].get('error', [])
                error_str = str(error_msgs) if error_msgs else "Unknown Error"
                raise Exception(f"Bulk attendance update failed: {state}. Details: {error_str}")
        except KeyError:
            raise Exception(f"Failed to read state from updateServiceDelivery response. Data: {data}")
