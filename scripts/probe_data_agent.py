import os
import requests
import google.auth
import google.auth.transport.requests
import json

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
    print(f"Probing Agent: {agent_id_full}")
    
    # Probe Assistant
    parts = agent_id_full.split("/")
    # .../assistants/default_assistant
    if "assistants" in parts:
        idx = parts.index("assistants")
        asst_path = "/".join(parts[:idx+2]) # .../default_assistant
        
        print(f"\n--- Probing Assistant: {asst_path}")
        
        # 1. Sessions
        url = f"https://discoveryengine.googleapis.com/v1alpha/{asst_path}/sessions"
        print(f"POST {url}")
        resp = requests.post(url, headers=headers, json={"user_pseudo_id": "test-asst"})
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            sess = resp.json()
            print(f"Session: {sess['name']}")
            # Converse
            url2 = f"https://discoveryengine.googleapis.com/v1alpha/{sess['name']}:converse"
            print(f"POST {url2}")
            resp2 = requests.post(url2, headers=headers, json={"query": {"input": "Hello"}})
            print(f"Status: {resp2.status_code}")
            print(f"Response: {resp2.text}")
            
        # 2. Query
        url = f"https://discoveryengine.googleapis.com/v1alpha/{asst_path}:query"
        print(f"POST {url}")
        resp = requests.post(url, headers=headers, json={"query": "Hello"})
        print(f"Status: {resp.status_code}")

    # 1. Try create session on Agent
    url_sessions = f"https://discoveryengine.googleapis.com/v1alpha/{agent_id_full}/sessions"
    print(f"\n--- Attempt 1: POST {url_sessions}")
    resp = requests.post(url_sessions, headers=headers, json={"user_pseudo_id": "test-user"})
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    # 2. Try direct converse (stateless?)
    url_converse = f"https://discoveryengine.googleapis.com/v1alpha/{agent_id_full}:converse"
    print(f"\n--- Attempt 2: POST {url_converse}")
    resp = requests.post(url_converse, headers=headers, json={"query": {"input": "Hello"}})
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    # 3. Try direct query
    url_query = f"https://discoveryengine.googleapis.com/v1alpha/{agent_id_full}:query"
    print(f"\n--- Attempt 3: POST {url_query}")
    resp = requests.post(url_query, headers=headers, json={"query": "Hello"})
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")

if __name__ == "__main__":
    # Use the Agent ID from a likely existing agent
    # Resource: projects/679926387543/locations/global/collections/default_collection/engines/gemini-enterprise-17634901_1763490144996/assistants/default_assistant/agents/12174119476964308525
    agent_res = "projects/679926387543/locations/global/collections/default_collection/engines/gemini-enterprise-17634901_1763490144996/assistants/default_assistant/agents/12174119476964308525"
    probe(agent_res)
