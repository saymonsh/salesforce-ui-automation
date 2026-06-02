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
            var auraToken = window.__sniffedAuraToken || "";
            var contextStr = window.__sniffedAuraContext || "";
            var fwuid = "";
            
            if (!auraToken && window.auraConfig && window.auraConfig.token) {
                auraToken = window.auraConfig.token;
            }
            if (!contextStr && window.auraConfig && window.auraConfig.context) {
                contextStr = JSON.stringify(window.auraConfig.context);
            }
            
            if (typeof $A !== 'undefined') {
                if (!auraToken) {
                    try { auraToken = $A.get("$A.token"); } catch(e) {}
                }
                if (!contextStr) {
                    try { contextStr = $A.getContext().encodeForServer(); } catch(e) {}
                }
            }
            
            // Fallback: search all scripts for token and fwuid
            if (!auraToken || !contextStr) {
                var scripts = document.getElementsByTagName('script');
                for (var i = 0; i < scripts.length; i++) {
                    var content = scripts[i].innerHTML;
                    if (!content) continue;
                    
                    if (!auraToken) {
                        var mToken = content.match(/"token"\\s*:\\s*"(eyJ[^"]+)"/);
                        if (mToken) auraToken = mToken[1];
                    }
                    if (!fwuid) {
                        var mFwuid = content.match(/"fwuid"\\s*:\\s*"([^"]+)"/);
                        if (mFwuid) fwuid = mFwuid[1];
                    }
                }
            }
            
            if (!contextStr && fwuid) {
                contextStr = JSON.stringify({
                    "mode": "PROD",
                    "app": "one:one",
                    "pathPrefix": "",
                    "fwuid": fwuid
                });
            }
            
            if (!auraToken) {
                callback({success: false, error: "Aura Token is missing! Could not extract from sniffer or page scripts."});
                return;
            }
            if (!contextStr) {
                callback({success: false, error: "Aura Context is missing! Could not extract from sniffer or page scripts."});
                return;
            }
            
            var bodyData = new URLSearchParams();
            bodyData.append('message', JSON.stringify(payload));
            bodyData.append('aura.token', auraToken);
            bodyData.append('aura.context', contextStr);
            bodyData.append('aura.pageURI', location.pathname);

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
                var match = text.match(/({[\\s\\S]*})/);
                if (match) {
                    try {
                        var data = JSON.parse(match[1]);
                        if (data.event && data.event.descriptor && data.event.descriptor.indexOf("clientOutOfSync") !== -1) {
                            callback({success: false, error: "Aura Client Out Of Sync. Please refresh the page and try again."});
                            return;
                        }
                        callback({success: true, data: data});
                    } catch(err) {
                        callback({success: false, error: err.message + " | Start of response: " + text.substring(0, 50)});
                    }
                } else {
                    callback({success: false, error: "No JSON found in response. Raw: " + text.substring(0, 50)});
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
                        "pageSize": 1999,
                        "pageToken": "0"
                    }
                }
            }]
        }
        
        data = self._execute_aura_request('/aura?r=1&aura.RelatedListUi.postRelatedListRecords=1', payload)
        
        print("\n=== GET PARTICIPANTS RESPONSE ===")
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("=================================\n")
        
        mapping = {}
        try:
            action = data.get('actions', [{}])[0]
            if action.get('state') == 'ERROR':
                raise Exception(f"Salesforce ERROR: {action.get('error')}")
                
            return_value = action.get('returnValue')
            if return_value is None:
                raise Exception(f"returnValue is None! Action data: {action}")
                
            records = return_value.get('records', [])
            for rec in records:
                sfdc_id = rec.get('id')
                id_num = rec.get('fields', {}).get('Pa_ID_Number__c', {}).get('value')
                if id_num:
                    mapping[str(id_num)] = sfdc_id
        except Exception as e:
            raise Exception(f"Error parsing participants response: {e}, Data: {data}")
            
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
                        # Field set mirrors the manual UI createRecord payload verbatim
                        # (captured from a HAR of manual entry) so Salesforce-side
                        # defaulting/validation behaves identically.
                        "fields": {
                            "Name": None,
                            "Pa_Communication_Type__c": None,
                            "Pa_Group_Comment__c": None,
                            "Pa_Group_Subject__c": None,
                            "Pa_Group_Teacher__c": None,
                            "Pa_Is_Cancelled__c": False,
                            "Pa_Service_Schedule__c": parent_record_id,
                            "Pa_Service_Session_Id__c": None,
                            "Pa_Session_End_DateTime__c": end_dt_utc,
                            "Pa_Session_Reported_Date__c": None,
                            "Pa_Session_Start_DateTime__c": start_dt_utc
                        }
                    }
                }
            }]
        }
        
        data = self._execute_aura_request('/aura?r=2&aura.RecordUi.createRecord=1', payload)
        
        print("\n=== CREATE SESSION RESPONSE ===")
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("=================================\n")
        
        try:
            action = data.get('actions', [{}])[0]
            if action.get('state') == 'ERROR':
                raise Exception(f"Salesforce ERROR: {action.get('error')}")
                
            return_value = action.get('returnValue')
            if return_value is None:
                raise Exception(f"returnValue is None! Action data: {action}")
                
            session_id = return_value.get('id')
            return session_id
        except Exception as e:
            raise Exception(f"Failed to extract Session ID from createRecord response. Error: {e}, Data: {data}")

    def start_create_sd_flow(self, session_id):
        """Start the 'Pa_Create_Service_Delivery' screen flow for the given session.

        In the Salesforce UI the per-participant Service Delivery records are NOT
        auto-created when a Pa_Service_Session__c is inserted. They are created by
        this Quick Action flow, which commits them already at startFlow and renders
        them in its 'ServiceDeliveryTable' screen component. We read the created
        records back out of that screen component's inputs.

        Returns (serialized_state, delivery_records) where serialized_state must be
        echoed back to finish_create_sd_flow to finalize the interview.
        """
        payload = {
            "actions": [{
                "id": "5;a",
                "descriptor": "aura://FlowRuntimeConnectController/ACTION$startFlow",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "flowDevName": "Pa_Create_Service_Delivery",
                    "arguments": json.dumps([
                        {"name": "recordId", "type": "String", "value": session_id}
                    ]),
                    "enableTrace": False,
                    "enableRollbackMode": False,
                    "debugAsUserId": "",
                    "useLatestSubflow": False,
                    "isBuilderDebug": False
                }
            }]
        }

        data = self._execute_aura_request('/aura?r=5&aura.FlowRuntimeConnect.startFlow=1', payload)

        try:
            action = data.get('actions', [{}])[0]
            if action.get('state') == 'ERROR':
                raise Exception(f"Salesforce ERROR: {action.get('error')}")

            return_value = action.get('returnValue')
            if return_value is None:
                raise Exception(f"returnValue is None! Action data: {action}")

            response = return_value.get('response') or {}
            if response.get('error'):
                raise Exception(f"Flow error: {response.get('error')}")

            serialized_state = response.get('serializedEncodedState')
            if not serialized_state:
                raise Exception(f"startFlow returned no serializedEncodedState. Response keys: {list(response.keys())}")

            delivery_records = []
            for field in response.get('fields', []):
                if field.get('name') == 'ServiceDeliveryTable':
                    for inp in field.get('inputs', []):
                        if inp.get('name') == 'deliveryRecords':
                            delivery_records = inp.get('value') or []
        except Exception as e:
            raise Exception(f"Error parsing startFlow response: {e}")

        print(f"\n=== START SD FLOW: created {len(delivery_records)} service delivery record(s) ===\n")
        return serialized_state, delivery_records

    def finish_create_sd_flow(self, serialized_state, delivery_records):
        """Advance the 'Pa_Create_Service_Delivery' flow to FINISHED.

        Mirrors the manual UI's navigateFlow(NEXT): the delivery records are echoed
        back verbatim (attendance statuses are persisted separately via
        report_attendance/updateServiceDelivery, not through the flow). Finishing the
        flow runs its post-processing side-effects (e.g. activating the related
        Program Engagement).
        """
        payload = {
            "actions": [{
                "id": "6;a",
                "descriptor": "aura://FlowRuntimeConnectController/ACTION$navigateFlow",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "request": {
                        "action": "NEXT",
                        "serializedState": serialized_state,
                        "fields": [
                            {
                                "field": "ServiceDeliveryTable.deliveryRecords",
                                "value": delivery_records,
                                "isVisible": True
                            },
                            {
                                "field": "ServiceDeliveryTable.relevantObjectApiName",
                                "value": "",
                                "isVisible": True
                            }
                        ],
                        "uiElementVisited": True,
                        "enableTrace": False,
                        "lcErrors": {},
                        "isBuilderDebug": False
                    }
                }
            }]
        }

        data = self._execute_aura_request('/aura?r=6&aura.FlowRuntimeConnect.navigateFlow=1', payload)

        try:
            action = data.get('actions', [{}])[0]
            if action.get('state') == 'ERROR':
                raise Exception(f"Salesforce ERROR: {action.get('error')}")

            return_value = action.get('returnValue')
            if return_value is None:
                raise Exception(f"returnValue is None! Action data: {action}")

            response = return_value.get('response') or {}
            status = response.get('interviewStatus')
            if status != 'FINISHED':
                raise Exception(f"Flow did not finish cleanly. interviewStatus={status}, error={response.get('error')}")
        except Exception as e:
            raise Exception(f"Error parsing navigateFlow response: {e}")

        print("\n=== FINISH SD FLOW: interview FINISHED ===\n")

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
        
        print("\n=== REPORT ATTENDANCE RESPONSE ===")
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("=================================\n")
        
        try:
            action = data.get('actions', [{}])[0]
            state = action.get('state')
            if state != 'SUCCESS':
                error_msgs = action.get('error', [])
                error_str = str(error_msgs) if error_msgs else "Unknown Error"
                raise Exception(f"Bulk attendance update failed: {state}. Details: {error_str}")
        except Exception as e:
            raise Exception(f"Failed to read state from updateServiceDelivery response. Error: {e}, Data: {data}")
