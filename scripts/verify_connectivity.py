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

def debug_simple():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")

    headers = get_auth_headers(project_id)
    host = "discoveryengine.googleapis.com" if location == "global" else f"{location}-discoveryengine.googleapis.com"
    base_beta = f"https://{host}/v1beta/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}"
    
    # Create Session
    session_url = f"{base_beta}/sessions"
    s_resp = requests.post(session_url, headers=headers, json={"user_pseudo_id": "test-user-simple"})
    if s_resp.status_code == 200:
        session_name = s_resp.json()["name"]
    else:
        print("Session creation failed")
        return

    print(f"Session: {session_name}")
    
    # 1. Test :answer with simple text
    answer_url = f"{base_beta}/servingConfigs/default_search:answer"
    print(f"\nProbing Answer: {answer_url}")
    
    payloads = [
        {
            "name": "Query BigQuery",
            "json": {
                "query": {"text": "Query BigQuery for count of customers in Washington."},
                "session": session_name
            }
        },
        {
             "name": "Params Agent Spec (v1Spec?)",
             "json": {
                 "query": {"text": "audit_test"},
                 "params": {
                     "agentSpec": {"agentId": agent_id}
                 },
                 "session": session_name
             }
        }
    ]
    
    for p in payloads:
        print(f"\n--- {p['name']} ---")
        resp = requests.post(answer_url, headers=headers, json=p['json'])
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2)[:1000])
        else:
            print(f"Error: {resp.text[:500]}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    debug_simple()
