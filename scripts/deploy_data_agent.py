import os
import requests
import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv
import time

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

def deploy_agent():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")
    bq_dataset_id = os.getenv("BQ_DATASET_ID")
    
    if not all([project_id, location, engine_id, bq_dataset_id]):
        print(f"Missing required environment variables:")
        print(f"  GOOGLE_CLOUD_PROJECT: {project_id}")
        print(f"  DIA_LOCATION: {location}")
        print(f"  DIA_ENGINE_ID: {engine_id}")
        print(f"  BQ_DATASET_ID: {bq_dataset_id}")
        return

    print(f"Deploying Agent to Project: {project_id}, Location: {location}, Engine: {engine_id}")
    
    headers = get_auth_headers(project_id)
    
    if location == "global":
        host = "discoveryengine.googleapis.com"
    else:
        host = f"{location}-discoveryengine.googleapis.com"

    base_url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant"
    
    # 1. List Agents
    agents_url = f"{base_url}/agents"
    print(f"Listing agents at: {agents_url}")
    resp = requests.get(agents_url, headers=headers)
    if resp.status_code != 200:
        print(f"Failed to list agents: {resp.text}")
        return

    agents = resp.json().get("agents", [])
    target_agent_display_name = "Automated Data Agent"
    existing_agent = None
    
    for a in agents:
        if a.get("displayName") == target_agent_display_name:
            existing_agent = a
            break
            
    if existing_agent:
        print(f"Agent '{target_agent_display_name}' already exists.")
        print(f"Agent ID: {existing_agent['name'].split('/')[-1]}")
        print(f"Full Name: {existing_agent['name']}")
        return existing_agent['name'].split('/')[-1]
    
    # 2. Create Agent
    print(f"Creating agent '{target_agent_display_name}'...")
    
    payload = {
        "displayName": target_agent_display_name,
        "description": "Automated Data Agent for BigQuery analysis",
        "managed_agent_definition": {
            "tool_settings": {
                "tool_description": "Use this agent to query BigQuery data about customers and orders."
            },
            "data_science_agent_config": {
                "bq_project_id": project_id,
                "bq_dataset_id": bq_dataset_id,
                "nl_query_config": {
                    "nl2sql_prompt": "You are a specialized Data Scientist agent. Your job is to query the BigQuery database to answer user questions."
                }
            }
        }
    }
    
    agent_id = f"data-agent-{int(time.time())}"
    params = {"agentId": agent_id}
    
    resp = requests.post(agents_url, headers=headers, json=payload)
    if resp.status_code == 200:
        new_agent = resp.json()
        print("Agent created successfully!")
        print(f"Agent ID: {new_agent['name'].split('/')[-1]}")
        print(f"Full Name: {new_agent['name']}")
        return new_agent['name'].split('/')[-1]
    else:
        print(f"Failed to create agent: {resp.status_code} - {resp.text}")
        return None

if __name__ == "__main__":
    deploy_agent()
