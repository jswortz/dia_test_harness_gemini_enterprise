import os
import requests
import google.auth
import google.auth.transport.requests
import json

def inspect_agent():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")
    
    creds, _ = google.auth.default()
    creds.refresh(google.auth.transport.requests.Request())
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "X-Goog-User-Project": project_id
    }
    
    host = "discoveryengine.googleapis.com"
    if location != "global":
        host = f"{location}-discoveryengine.googleapis.com"

    parent = f"projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant"
    url = f"https://{host}/v1alpha/{parent}/agents"
    
    print(f"Listing Agents from: {url}")
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        agents = resp.json().get("agents", [])
        for a in agents:
            print(f"Name: {a.get('name')}")
            print(f"Display Name: {a.get('displayName')}")
    else:
        print(f"Error: {resp.text}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    inspect_agent()
