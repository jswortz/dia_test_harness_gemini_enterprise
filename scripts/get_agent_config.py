#!/usr/bin/env python3
"""
Get agent configuration via REST API call.

This script only requires GOOGLE_CLOUD_PROJECT (Discovery Engine project) since it's
just reading the agent configuration. The returned config will contain bq_project_id
and bq_dataset_id that were set during agent creation.
"""

import os
import sys
import requests
import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv
from pathlib import Path
import json

# Load environment variables from evalset/.env
script_dir = Path(__file__).parent
evalset_dir = script_dir.parent
env_path = evalset_dir / ".env"
load_dotenv(env_path)

def get_auth_headers(project_id):
    """Get authentication headers for API requests."""
    creds, _ = google.auth.default(quota_project_id=project_id)
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }

def get_agent_config(agent_id_override=None):
    """Get agent configuration via REST API."""
    # Read environment variables from .env
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = agent_id_override or os.getenv("DIA_AGENT_ID")
    
    # Validate required environment variables
    missing = []
    if not project_id:
        missing.append("GOOGLE_CLOUD_PROJECT")
    if not engine_id:
        missing.append("DIA_ENGINE_ID")
    if not agent_id:
        missing.append("DIA_AGENT_ID")
    
    if missing:
        print(f"❌ Missing required environment variables: {', '.join(missing)}")
        print(f"\nPlease ensure your .env file at {env_path} contains:")
        for var in missing:
            print(f"  {var}=<value>")
        sys.exit(1)
    
    # Build API host
    if location == "global":
        host = "discoveryengine.googleapis.com"
    else:
        host = f"{location}-discoveryengine.googleapis.com"
    
    # Build agent resource name
    agent_name = (
        f"projects/{project_id}/locations/{location}/collections/default_collection/"
        f"engines/{engine_id}/assistants/default_assistant/agents/{agent_id}"
    )
    
    # Build URL
    url = f"https://{host}/v1alpha/{agent_name}"
    
    print(f"Fetching agent config from: {url}")
    print(f"Agent ID: {agent_id}\n")
    
    # Get auth headers
    headers = get_auth_headers(project_id)
    
    # Make GET request
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        agent_config = response.json()
        print("✓ Successfully retrieved agent configuration\n")
        print("=" * 80)
        print("AGENT CONFIGURATION")
        print("=" * 80)
        print(json.dumps(agent_config, indent=2))
        return agent_config
    else:
        print(f"❌ Failed to get agent config: {response.status_code}")
        print(f"Response: {response.text}")
        return None

if __name__ == "__main__":
    # Allow agent ID to be passed as command-line argument
    agent_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    get_agent_config(agent_id_override=agent_id_arg)
