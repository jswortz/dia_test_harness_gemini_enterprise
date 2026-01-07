import os
import json
import logging
import requests
import google.auth
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.DEBUG)

def get_project_number(project_id, credentials):
    """Fetches project number using Resource Manager API."""
    try:
        from googleapiclient import discovery
        service = discovery.build('cloudresourcemanager', 'v1', credentials=credentials)
        request = service.projects().get(projectId=project_id)
        response = request.execute()
        return response['projectNumber']
    except Exception as e:
        logging.warning(f"Could not fetch project number: {e}")
        return None

def debug_query():
    load_dotenv()
    project_id = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")

    print(f"DEBUG: Project={project_id}, Location={location}, Engine={engine_id}, Agent={agent_id}")

    credentials, _ = google.auth.default()
    if not credentials.valid:
        credentials.refresh(Request())

    # Try to get project number for the session string
    # project_number = get_project_number(project_id, credentials)
    # For now, let's try with project_id first as per current implementation, 
    # but logging it to see if we should change it.
    
    base_url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}"
    url = f"{base_url}/assistants/default_assistant:streamAssist"
    
    session_name = f"projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/sessions/-"
    
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }

    payload = {
        "session": session_name,
        "query": {
            "text": "How many customers are there?"
        },
        # CRITICAL: agentsSpec
        "agentsSpec": {
            "agentSpecs": [
                {"agentId": agent_id}
            ]
        }
    }

    print(f"\nDEBUG: Sending Payload:\n{json.dumps(payload, indent=2)}")
    
    response = requests.post(url, headers=headers, json=payload)
    print(f"\nDEBUG: Response Status: {response.status_code}")
    
    if response.ok:
        print("DEBUG: Response Content (First 500 chars):")
        print(response.text[:500])
        try:
            # Try to parse all lines
            for line in response.text.splitlines():
                if line.strip():
                    data = json.loads(line)
                    # output relevant parts
                    if 'answer' in data:
                        print(f"DEBUG: Found answer chunk: {str(data['answer'])[:200]}...")
        except Exception as e:
            print(f"DEBUG: Parsing error: {e}")
    else:
        print(f"DEBUG: Response Error: {response.text}")

if __name__ == "__main__":
    debug_query()
