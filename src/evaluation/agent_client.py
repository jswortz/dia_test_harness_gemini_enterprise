import json
import logging
import requests
import google.auth
from google.auth.transport.requests import Request
from typing import Dict, Any, Optional


class AgentAuthorizationError(Exception):
    """Raised when agent requires OAuth authorization (403 error)."""
    def __init__(self, agent_id: str, project_id: str, location: str, engine_id: str):
        self.agent_id = agent_id
        self.project_id = project_id
        self.location = location
        self.engine_id = engine_id
        super().__init__(f"Agent {agent_id} requires OAuth authorization")


class AgentClient:
    def __init__(self, project_id: str, location: str, engine_id: str, agent_id: str):
        self.project_id = project_id
        self.location = location
        self.engine_id = engine_id
        self.agent_id = agent_id
        
        # Use regional endpoint for non-global locations
        if location == "global":
            api_endpoint = "https://discoveryengine.googleapis.com"
        else:
            api_endpoint = f"https://{location}-discoveryengine.googleapis.com"
        
        self.base_url = f"{api_endpoint}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}"
        self.credentials, _ = google.auth.default()

    def _get_headers(self) -> Dict[str, str]:
        if not self.credentials.valid:
            self.credentials.refresh(Request())
        return {
            "Authorization": f"Bearer {self.credentials.token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": self.project_id
        }

    def create_session(self) -> str:
        """Creates a session and returns the session name."""
        url = f"{self.base_url}/sessions"
        headers = self._get_headers()
        payload = {"displayName": "GoldenTestSession"}
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["name"]

    def query_agent(self, text: str, session_id: Optional[str] = None) -> list:
        """
        Queries the agent using streamAssist endpoint.

        CRITICAL: Uses agentsSpec to route to the Data Insights Agent.
        Without agentsSpec, queries would go to the default assistant, not the DIA.

        Returns:
            List of streaming message chunks as shown in API response structure.
        """
        if not session_id:
            # Use '-' for auto-created session
            session_name = f"projects/{self.project_id}/locations/{self.location}/collections/default_collection/engines/{self.engine_id}/sessions/-"
        else:
            session_name = session_id

        url = f"{self.base_url}/assistants/default_assistant:streamAssist"
        headers = self._get_headers()

        # CRITICAL: Include agentsSpec to route to Data Insights Agent
        # The agentId can be either the numeric ID or the full resource name
        # Try with full resource name first
        agent_resource_name = f"projects/{self.project_id}/locations/{self.location}/collections/default_collection/engines/{self.engine_id}/assistants/default_assistant/agents/{self.agent_id}"
        
        payload = {
            "session": session_name,
            "query": {
                "text": text
            },
            "agentsSpec": {
                "agentSpecs": [
                    {"agentId": agent_resource_name}
                ]
            }
        }

        logging.info(f"Querying agent {self.agent_id} with: {text}")
        response = requests.post(url, headers=headers, json=payload)

        if not response.ok:
            # Check for 403 authorization errors
            if response.status_code == 403:
                logging.error(f"Agent requires authorization (403 Forbidden)")
                logging.error(f"Response body: {response.text}")
                raise AgentAuthorizationError(
                    agent_id=self.agent_id,
                    project_id=self.project_id,
                    location=self.location,
                    engine_id=self.engine_id
                )

            logging.error(f"Request failed with status {response.status_code}")
            logging.error(f"Response body: {response.text}")
            logging.error(f"Payload sent: {json.dumps(payload)}")
            response.raise_for_status()

        # streamAssist returns a JSON array of streaming messages
        # Structure: [{answer: {replies: [...]}}, {answer: {replies: [...]}}, {sessionInfo: {...}}]
        try:
            result = response.json()
            # Ensure we return a list (the streaming messages array)
            if isinstance(result, list):
                return result
            else:
                # Wrap single response in list for consistency
                return [result]
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON response: {e}")
            logging.error(f"Response text: {response.text}")
            raise

