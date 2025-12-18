import os
import requests
import google.auth
import google.auth.transport.requests
import json
import uuid

def get_headers():
    creds, project = google.auth.default()
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project
    }

def probe(agent_id_full):
    headers = get_headers()
    parts = agent_id_full.split("/")
    engine_path = "/".join(parts[:8]) # projects/.../engines/ID
    
    # 1. Create Session (v1alpha)
    url_sess = f"https://discoveryengine.googleapis.com/v1alpha/{engine_path}/sessions"
    print(f"Creating Session: {url_sess}")
    resp = requests.post(url_sess, headers=headers, json={"user_pseudo_id": f"test-{uuid.uuid4()}"})
    if resp.status_code != 200:
        print(f"Session failed: {resp.text}")
        return
    
    session_name = resp.json()["name"]
    print(f"Session: {session_name}")
    
    # 2. Answer (v1alpha)
    # Try default_search
    url_ans = f"https://discoveryengine.googleapis.com/v1alpha/{engine_path}/servingConfigs/default_search:answer"
    print(f"Probing: {url_ans}")
    
    payloads = [
        # Standard
        {"query": {"text": "Hello"}}, 
        # With session
        {"query": {"text": "Hello"}, "session": session_name},
        # With agent spec
        {"query": {"text": "Hello"}, "session": session_name, "spec": {"agentSpec": {"agent": agent_id_full}}},
         # With params agent
        {"query": {"text": "Hello"}, "session": session_name, "params": {"agent": agent_id_full}},
        # With user input (v1beta style? v1alpha might use query.text)
    ]
    
    for i, p in enumerate(payloads):
        print(f"\n--- Payload {i}")
        print(json.dumps(p))
        resp = requests.post(url_ans, headers=headers, json=p)
        print(f"Status: {resp.status_code}")
        # print(f"Response: {resp.text[:200]}") # Truncate

if __name__ == "__main__":
    agent_res = "projects/679926387543/locations/global/collections/default_collection/engines/gemini-enterprise-17634901_1763490144996/assistants/default_assistant/agents/12174119476964308525"
    probe(agent_res)
