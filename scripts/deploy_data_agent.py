import os
import requests
import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv
import time
import json
import uuid

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

def create_authorization(project_id, location, headers, host):
    client_id = os.getenv("OAUTH_CLIENT_ID")
    client_secret = os.getenv("OAUTH_SECRET")
    
    if not client_id or not client_secret:
        print("Skipping Authorization: OAUTH_CLIENT_ID or OAUTH_SECRET not set.")
        return None

    auth_id = f"auth-{uuid.uuid4()}"
    # auth_uri must include specific params for BigQuery access and Vertex AI Search redirect
    auth_uri = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        "&redirect_uri=https%3A%2F%2Fvertexaisearch.cloud.google.com%2Fstatic%2Foauth%2Foauth.html"
        "&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fbigquery"
        "&include_granted_scopes=true"
        "&response_type=code"
        "&access_type=offline"
        "&prompt=consent"
    )
    token_uri = "https://oauth2.googleapis.com/token"

    parent = f"projects/{project_id}/locations/{location}"
    url = f"https://{host}/v1alpha/{parent}/authorizations?authorizationId={auth_id}"
    
    payload = {
        "name": f"{parent}/authorizations/{auth_id}",
        "serverSideOauth2": {
            "clientId": client_id,
            "clientSecret": client_secret,
            "authorizationUri": auth_uri,
            "tokenUri": token_uri
        }
    }
    
    print(f"Creating Authorization resource: {auth_id}")
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code == 200:
        auth_name = resp.json()["name"]
        print(f"Authorization created: {auth_name}")
        return auth_name
    else:
        print(f"Failed to create authorization: {resp.status_code} - {resp.text}")
        return None

def delete_agent(agent_name, headers):
    url = f"https://discoveryengine.googleapis.com/v1alpha/{agent_name}"
    print(f"Deleting agent: {agent_name}...")
    resp = requests.delete(url, headers=headers)
    if resp.status_code == 200:
        print("Agent deleted successfully.")
        # Wait a bit for deletion to propagate
        time.sleep(5)
    else:
        print(f"Failed to delete agent: {resp.status_code} - {resp.text}")

def deploy_agents_from_config():
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

    print(f"Deploying Agents to Project: {project_id}, Location: {location}, Engine: {engine_id}")
    
    headers = get_auth_headers(project_id)
    
    if location == "global":
        host = "discoveryengine.googleapis.com"
    else:
        host = f"{location}-discoveryengine.googleapis.com"

    base_url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant"
    
    # Load configs
    with open("configs/multi_variant.json", "r") as f:
        agent_configs = json.load(f)

    for config in agent_configs:
        config_name = config["name"]
        print(f"\nProcessing variant: {config_name}")
        
        # Construct Display Name
        target_agent_display_name = f"Data Agent - {config_name}"
        
        # 1. List Agents to check existence
        agents_url = f"{base_url}/agents"
        resp = requests.get(agents_url, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to list agents: {resp.text}")
            continue

        agents = resp.json().get("agents", [])
        existing_agent = None
        
        for a in agents:
            if a.get("displayName") == target_agent_display_name:
                existing_agent = a
                break
                
        if existing_agent:
            print(f"Agent '{target_agent_display_name}' already exists. Deleting to recreate with Auth...")
            delete_agent(existing_agent['name'], headers)
            existing_agent = None
        
        # Create Authorization
        auth_resource = create_authorization(project_id, location, headers, host)

        # Prepare data_science_config
        data_science_config = {
            "bq_project_id": project_id,
            "bq_dataset_id": bq_dataset_id,
            "nl_query_config": {}
        }
        
        # Check for new 'dataScienceAgentConfig' structure
        if "dataScienceAgentConfig" in config:
            ds_config = config["dataScienceAgentConfig"]
            nl_query = ds_config.get("nlQueryConfig", {})
            
            if "nl2sqlPrompt" in nl_query:
                data_science_config["nl_query_config"]["nl2sqlPrompt"] = nl_query["nl2sqlPrompt"]
            if "nl2pyPrompt" in nl_query:
                 data_science_config["nl_query_config"]["nl2pyPrompt"] = nl_query["nl2pyPrompt"]
            if "nl2sqlExample" in nl_query:
                 data_science_config["nl_query_config"]["nl2sqlExamples"] = nl_query["nl2sqlExample"]
            if "schemaDescription" in nl_query:
                 data_science_config["nl_query_config"]["schemaDescription"] = nl_query["schemaDescription"]
        else:
            # Legacy support
            nl2sql_prompt = config.get("nl2sql_prompt", "")
            params = config.get("params", {})
            if "schema_context" in params:
                nl2sql_prompt += "\n\nSchema Context:\n" + params["schema_context"]
            
            data_science_config["nl_query_config"]["nl2sqlPrompt"] = nl2sql_prompt
            if "nl2py_prompt" in params:
                 data_science_config["nl_query_config"]["nl2pyPrompt"] = params["nl2py_prompt"]
            if "nl2sql_example" in params:
                 data_science_config["nl_query_config"]["nl2sqlExample"] = params["nl2sql_example"]
            if "schema_description" in params:
                 data_science_config["nl_query_config"]["schemaDescription"] = params["schema_description"]


        
        payload = {
            "displayName": target_agent_display_name,
            "description": config.get("description", "Automated Data Agent"),
            "managed_agent_definition": {
                "tool_settings": {
                    "tool_description": "Use this agent to query BigQuery data about customers and orders."
                },
                "data_science_agent_config": data_science_config
            }
        }

        if auth_resource:
            payload["authorization_config"] = {
                "tool_authorizations": [auth_resource]
            }
        
        resp = requests.post(agents_url, headers=headers, json=payload)
        agent_name = ""
        
        if resp.status_code == 200:
            new_agent = resp.json()
            print("Agent created successfully!")
            agent_name = new_agent['name']
            print(f"Agent ID: {agent_name.split('/')[-1]}")
            print(f"Full Name: {agent_name}")
        else:
            print(f"Failed to create agent: {resp.status_code} - {resp.text}")
            continue

        # 3. Deploy Agent explicitly
        print(f"Deploying agent '{target_agent_display_name}'...")
        deploy_url = f"https://{host}/v1alpha/{agent_name}:deploy"
        deploy_resp = requests.post(deploy_url, headers=headers, json={"name": agent_name})
        
        if deploy_resp.status_code == 200:
            lro = deploy_resp.json()
            print(f"Deployment LRO started: {lro.get('name')}")
        elif deploy_resp.status_code == 400 and "Invalid agent state for deploy: ENABLED" in deploy_resp.text:
             print("Agent already enabled.")
        else:
            print(f"Failed to deploy agent: {deploy_resp.status_code} - {deploy_resp.text}")

if __name__ == "__main__":
    deploy_agents_from_config()
