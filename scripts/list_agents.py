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

def list_agents():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")
    
    headers = get_auth_headers(project_id)
    
    if location == "global":
        host = "discoveryengine.googleapis.com"
    else:
        host = f"{location}-discoveryengine.googleapis.com"

    base_url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant"
    
    agents_url = f"{base_url}/agents"
    print(f"Listing Agents from: {agents_url}")
    
    resp = requests.get(agents_url, headers=headers)
    if resp.status_code == 200:
        agents = resp.json().get("agents", [])
        print(f"Found {len(agents)} agents:")
        for a in agents:
            print(f"- {a['displayName']} ({a['name'].split('/')[-1]}) [State: {a.get('state', 'UNKNOWN')}]")
            # print(a['name'])
    else:
        print(f"Failed to list agents: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    list_agents()
