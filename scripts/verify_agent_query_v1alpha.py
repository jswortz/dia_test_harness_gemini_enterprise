import os
import requests
import google.auth
import google.auth.transport.requests
import time
import uuid
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_auth_headers(project_id):
    creds, _ = google.auth.default(quota_project_id=project_id)
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return {
        "Authorization": f"Bearer {creds.token}",
        "X-Goog-User-Project": project_id,
        "Content-Type": "application/json"
    }

def verify_agent_workflow():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID") # Persistent Engine
    bq_dataset_id = os.getenv("BQ_DATASET_ID")

    if not all([project_id, location, engine_id, bq_dataset_id]):
        logger.error("Missing env vars.")
        return

    headers = get_auth_headers(project_id)
    host = "discoveryengine.googleapis.com" if location == "global" else f"{location}-discoveryengine.googleapis.com"
    
    # 1. Create Agent
    parent = f"projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant"
    create_url = f"https://{host}/v1alpha/{parent}/agents"
    
    payload = {
        "displayName": f"Verification Agent",
        "description": "Temp agent for verification",
        "managed_agent_definition": {
            "data_science_agent_config": {
                "bq_project_id": project_id,
                "bq_dataset_id": bq_dataset_id,
                "nl_query_config": {
                    "nl2sql_prompt": "You are a test agent."
                }
            }
        }
    }
    
    logger.info(f"Creating Agent...")
    resp = requests.post(create_url, headers=headers, json=payload)
    if resp.status_code != 200:
        logger.error(f"Failed to create agent: {resp.text}")
        return

    new_agent = resp.json()
    agent_name = new_agent["name"]
    agent_id = agent_name.split("/")[-1]
    logger.info(f"Agent created: {agent_id}. Resource: {agent_name}")
    
    # 2. Deploy Agent (LRO)
    deploy_url = f"https://{host}/v1alpha/{agent_name}:deploy"
    logger.info(f"Deploying agent at {deploy_url}...")
    
    deploy_resp = requests.post(deploy_url, headers=headers, json={"name": agent_name})
    if deploy_resp.status_code != 200:
        logger.error(f"Deploy call failed: {deploy_resp.text}")
        return

    lro_name = deploy_resp.json()["name"]
    logger.info(f"Deployment started. LRO: {lro_name}. Polling...")
    
    # Poll LRO
    while True:
        lro_resp = requests.get(f"https://{host}/v1alpha/{lro_name}", headers=headers)
        if lro_resp.status_code != 200:
            logger.error(f"LRO poll failed: {lro_resp.text}")
            break
            
        lro_data = lro_resp.json()
        if lro_data.get("done"):
            if "error" in lro_data:
                logger.error(f"Deployment failed: {lro_data['error']}")
                return
            logger.info("Deployment complete!")
            break
        logger.info("Deploying...")
        time.sleep(5)
    
    # 3. Try Querying (v1alpha)
    agent_resource = agent_name # Full name
    query_url = f"https://{host}/v1alpha/{agent_resource}:query" # Or maybe sessions?
    
    # Let's try sessions first as that's more standard
    session_url = f"https://{host}/v1alpha/{agent_resource}/sessions"
    session_payload = {"user_pseudo_id": f"user-{uuid.uuid4()}"}
    
    logger.info(f"Creating Session at {session_url}...")
    sess_resp = requests.post(session_url, headers=headers, json=session_payload)
    
    if sess_resp.status_code == 200:
        session_name = sess_resp.json()['name']
        logger.info(f"Session created: {session_name}")
        
        # Try converse/query on session?
        # Endpoints might be :query or /conversations/...
        # Let's try the conversational API for agents
        converse_url = f"https://{host}/v1alpha/{session_name}:converse" # Or query
        
        logger.info(f"Probing {converse_url}...")
        conv_payload = {"query": {"input": "Count customers"}}
        conv_resp = requests.post(converse_url, headers=headers, json=conv_payload)
        logger.info(f"Converse Result: {conv_resp.status_code} {conv_resp.text}")
        
    else:
        logger.warning(f"Session creation failed: {sess_resp.status_code} {sess_resp.text}")
        # Could be that we need to query the agent directly without session for some endpoints?
        
        logger.info("Trying direct :query on agent...")
        direct_query_payload = {"query": {"text": "Count customers"}} # Guessing payload
        direct_resp = requests.post(query_url, headers=headers, json=direct_query_payload)
        logger.info(f"Direct Query Result: {direct_resp.status_code} {direct_resp.text}")

    # 3. Cleanup
    logger.info("Cleaning up...")
    del_url = f"https://{host}/v1alpha/{agent_resource}"
    requests.delete(del_url, headers=headers)

if __name__ == "__main__":
    verify_agent_workflow()
