import os
import requests
import json
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

def inspect_sc():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")

    if not all([project_id, location, engine_id]):
        print("Missing env vars.")
        return

    headers = get_auth_headers(project_id)
    host = "discoveryengine.googleapis.com" if location == "global" else f"{location}-discoveryengine.googleapis.com"
    
    sc_url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/servingConfigs/default_search"
    print(f"Getting SC: {sc_url}")
    
    resp = requests.get(sc_url, headers=headers)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2))
    else:
        print(resp.text)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    inspect_sc()
