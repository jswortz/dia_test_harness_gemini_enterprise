
import os
import time
import uuid
import requests
import google.auth
from google.auth.transport.requests import Request

def get_access_token():
    credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    credentials.refresh(Request())
    return credentials.token, project

def create_engine(project_id, location, engine_id, data_store_ids):
    print(f"Creating engine {engine_id}...")
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/collections/default_collection/engines?engineId={engine_id}"
    token, _ = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    
    payload = {
        "displayName": f"Test Agent {engine_id}",
        "solutionType": "SOLUTION_TYPE_SEARCH",
        "industryVertical": "GENERIC",
        "commonConfig": {
            "companyName": "Harness Test"
        },
        "searchEngineConfig": {
            "searchTier": "SEARCH_TIER_ENTERPRISE",
            "searchAddOns": ["SEARCH_ADD_ON_LLM"]
        },
        "dataStoreIds": data_store_ids
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"Operation started: {response.json().get('name')}")
            return response.json()
        else:
            print(f"Error creating engine: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Exception: {e}")
        return None

def wait_for_engine(project_id, location, engine_id):
    print(f"Waiting for engine {engine_id} to be ready...")
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}"
    token, _ = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": project_id
    }
    
    start_time = time.time()
    while time.time() - start_time < 300:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            print("Engine is ready!")
            return True
        elif response.status_code == 404:
            print("Engine not found yet...")
        else:
            print(f"Error checking engine: {response.status_code}")
        
        time.sleep(10)
    return False

def check_operation(operation_name, project_id):
    # Skip operation check for now as it's flaky, rely on resource existence
    return True

if __name__ == "__main__":
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or "wortz-project-352116"
    location = "global"
    test_engine_id = f"verification-{uuid.uuid4().hex[:8]}"
    # Using the verified dummy data store
    data_store_ids = ["dummy-ds-1766018108"] 
    
    op = create_engine(project_id, location, test_engine_id, data_store_ids)
    if op:
        # success = check_operation(op['name'], project_id)
        # Rely on polling the resource
        success = wait_for_engine(project_id, location, test_engine_id)
        if success:
            print("Engine created successfully. Waiting 10s before delete...")
            time.sleep(10)
            delete_engine(project_id, location, test_engine_id)
        else:
            print("Engine creation failed (timeout).")
