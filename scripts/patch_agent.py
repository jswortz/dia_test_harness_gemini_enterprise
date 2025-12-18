import os
import requests
import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv
import json

load_dotenv()

def get_auth_headers(project_id):
    path = f"https://discoveryengine.googleapis.com/v1alpha/projects/{project_id}"
    creds, _ = google.auth.default(quota_project_id=project_id)
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return {
        "Authorization": f"Bearer {creds.token}",
        "X-Goog-User-Project": project_id
    }

def patch_agent(agent_id, new_display_name):
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")
    
    headers = get_auth_headers(project_id)
    
    if location == "global":
        host = "discoveryengine.googleapis.com"
    else:
        host = f"{location}-discoveryengine.googleapis.com"
        
    # Endpoint: .../agents/{AGENT_ID}?updateMask=displayName
    url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant/agents/{agent_id}?updateMask=displayName"
    
    payload = {
        "displayName": new_display_name
    }
    
    print(f"Patching Agent {agent_id} to '{new_display_name}'...")
    resp = requests.patch(url, headers=headers, json=payload)
    
    if resp.status_code == 200:
        print("Agent patched successfully!")
        print(json.dumps(resp.json(), indent=2))
    else:
        print(f"Failed to patch agent: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    # ID for 'Data Agent - baseline'
    agent_id = "16994088282440686170"
    new_name = "BaselineAgent"
    patch_agent(agent_id, new_name)
