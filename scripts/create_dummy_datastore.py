import os
import requests
import json
import time
from google.auth import default
from google.auth.transport.requests import Request

def get_auth_headers(project_id):
    credentials, _ = default(quota_project_id=project_id)
    credentials.refresh(Request())
    return {
        "Authorization": f"Bearer {credentials.token}",
        "X-Goog-User-Project": project_id,
        "Content-Type": "application/json"
    }

def create_and_attach():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")

    if not all([project_id, location, engine_id]):
        print("Missing env vars.")
        return

    headers = get_auth_headers(project_id)
    host = "discoveryengine.googleapis.com" if location == "global" else f"{location}-discoveryengine.googleapis.com"
    
    collection_path = f"projects/{project_id}/locations/{location}/collections/default_collection"
    
    # 1. Create Dummy Data Store
    ds_id = f"dummy-ds-{int(time.time())}"
    ds_url = f"https://{host}/v1alpha/{collection_path}/dataStores?dataStoreId={ds_id}"
    
    print(f"Creating Data Store: {ds_id}")
    payload = {
        "displayName": "Dummy Data Store for Agent",
        "industryVertical": "GENERIC",
        "solutionTypes": ["SOLUTION_TYPE_SEARCH", "SOLUTION_TYPE_CHAT"],
        "contentConfig": "CONTENT_REQUIRED", # or PUBLIC_WEBSITE?
        # Trying minimal config
    }
    
    resp = requests.post(ds_url, headers=headers, json=payload)
    print(f"Create Status: {resp.status_code}")
    if resp.status_code == 200:
        # Operation returned
        op = resp.json()
        print(f"Operation: {op.get('name')}")
        # Wait for operation? For now assume fast or we can poll.
        # But DS creation might take a moment.
        # We can just try to attach it immediately, engine might wait.
        pass
    else:
        print(f"Create Failed: {resp.text}")
        if "already exists" not in resp.text:
            return

    # 2. Get Engine to find current Data Stores
    engine_url = f"https://{host}/v1alpha/{collection_path}/engines/{engine_id}"
    resp = requests.get(engine_url, headers=headers)
    if resp.status_code != 200:
        print(f"Get Engine Failed: {resp.text}")
        return
    
    engine = resp.json()
    current_ids = engine.get("dataStoreIds", [])
    print(f"Current Data Store IDs: {current_ids}")
    
    if ds_id in current_ids:
        print("Data store already attached.")
        return

    # 3. Attach Data Store
    new_ids = current_ids + [ds_id]
    patch_url = f"{engine_url}?updateMask=dataStoreIds"
    print(f"Patching Engine with new list (size {len(new_ids)})")
    
    patch_resp = requests.patch(patch_url, headers=headers, json={"dataStoreIds": new_ids})
    print(f"Patch Status: {patch_resp.status_code}")
    print(patch_resp.text)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    create_and_attach()
