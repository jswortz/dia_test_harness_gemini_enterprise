#!/usr/bin/env python3
"""Inspect a specific agent's full configuration."""

import os
import json
import requests
import google.auth
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()

def main():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")

    print(f"Inspecting Agent ID: {agent_id}")
    print(f"Project: {project_id}")
    print(f"Location: {location}")
    print(f"Engine: {engine_id}\n")

    credentials, _ = google.auth.default()
    if not credentials.valid:
        credentials.refresh(Request())

    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }

    # Construct agent resource name
    agent_name = f"projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant/agents/{agent_id}"

    url = f"https://discoveryengine.googleapis.com/v1alpha/{agent_name}"

    print(f"Fetching: {url}\n")

    response = requests.get(url, headers=headers)

    if response.ok:
        agent_config = response.json()
        print("="*60)
        print("AGENT CONFIGURATION")
        print("="*60)
        print(json.dumps(agent_config, indent=2))
    else:
        print(f"Error {response.status_code}: {response.text}")

if __name__ == "__main__":
    main()
