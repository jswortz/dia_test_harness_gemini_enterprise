import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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
    def __init__(
        self,
        project_id: str,
        location: str,
        engine_id: str,
        agent_id: str,
        max_connections: int = 100
    ):
        """
        Initialize agent client with configurable connection pool.

        Args:
            project_id: Google Cloud project ID
            location: Agent location (e.g., "global")
            engine_id: Discovery Engine ID
            agent_id: Agent ID
            max_connections: Maximum number of concurrent connections to support (default: 100)
                            Should be set to at least the number of parallel workers
        """
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

        # Configure session with dynamic connection pool to support arbitrary concurrency
        # pool_maxsize is set based on max_connections to avoid "Connection pool is full" warnings
        self.session = requests.Session()

        # Configure HTTPAdapter with pool size matching max workers
        # pool_connections: number of connection pools to cache (one per host)
        # pool_maxsize: maximum number of connections to save in the pool
        adapter = HTTPAdapter(
            pool_connections=10,  # Keep this at 10 (reasonable for caching per-host pools)
            pool_maxsize=max_connections,  # Dynamic based on concurrent workers
            max_retries=Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504]
            )
        )

        # Mount adapter for both http and https
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

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
        response = self.session.post(url, headers=headers, json=payload)
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
        # Use the numeric agent ID directly (not the full resource name)
        payload = {
            "session": session_name,
            "query": {
                "text": text
            },
            "agentsSpec": {
                "agentSpecs": [
                    {"agentId": self.agent_id}
                ]
            }
        }

        logging.info(f"Querying agent {self.agent_id} with: {text}")
        response = self.session.post(url, headers=headers, json=payload)

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

