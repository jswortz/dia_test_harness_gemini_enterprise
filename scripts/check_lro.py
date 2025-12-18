import os
import requests
import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv

load_dotenv()

def check_lro(lro_name):
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    creds, _ = google.auth.default(quota_project_id=project_id)
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "X-Goog-User-Project": project_id
    }
    
    url = f"https://discoveryengine.googleapis.com/v1alpha/{lro_name}"
    print(f"Checking LRO: {url}")
    resp = requests.get(url, headers=headers)
    print(resp.json())

import sys

# ... imports ...

if __name__ == "__main__":
    if len(sys.argv) > 1:
        lro = sys.argv[1]
    else:
        print("Usage: python check_lro.py <LRO_NAME>")
        lro = "projects/679926387543/locations/global/collections/default_collection/engines/gemini-enterprise-17634901_1763490144996/assistants/default_assistant/agents/8890263956887595898/operations/deploy-agent-14447487012979432072"
    
    check_lro(lro)
