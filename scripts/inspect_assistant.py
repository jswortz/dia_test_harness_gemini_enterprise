import os
import requests
import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv
import json

load_dotenv()

def inspect_assistant():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")
    
    creds, _ = google.auth.default(quota_project_id=project_id)
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "X-Goog-User-Project": project_id
    }
    
    host = "discoveryengine.googleapis.com"
    if location != "global":
        host = f"{location}-discoveryengine.googleapis.com"

    url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant"
    
    print(f"Inspecting Assistant at: {url}")
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2))
    else:
        print(f"Failed to inspect assistant: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    inspect_assistant()
