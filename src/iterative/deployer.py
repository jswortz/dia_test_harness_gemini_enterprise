"""
SingleAgentDeployer: Manages deployment and updates for a single Data Insights Agent.

Handles:
- Initial deployment (create + OAuth authorization)
- Prompt updates via PATCH API (preserves OAuth across iterations)
- Agent state management
"""

import os
import requests
import google.auth
import google.auth.transport.requests
import time
import uuid
from typing import Dict, Any, Optional


class SingleAgentDeployer:
    """
    Deploys and updates a single Data Insights Agent for iterative optimization.

    Uses:
    - v1alpha API for agent creation and patching
    - PATCH API for prompt updates (preserves OAuth authorization)
    - Delete-and-recreate only on first deployment
    """

    def __init__(self, project_id: str, location: str, engine_id: str, dataset_id: str):
        """
        Initialize deployer.

        Args:
            project_id: Google Cloud project ID
            location: Location (e.g., "global")
            engine_id: Discovery Engine ID
            dataset_id: BigQuery dataset ID
        """
        self.project_id = project_id
        self.location = location.lower()
        self.engine_id = engine_id
        self.dataset_id = dataset_id
        self.agent_id = None  # Stored after first deployment
        self.agent_name = None  # Full resource name
        self.agent_display_name = None

        # Determine API host
        if self.location == "global":
            self.host = "discoveryengine.googleapis.com"
        else:
            self.host = f"{self.location}-discoveryengine.googleapis.com"

        self.base_url = (
            f"https://{self.host}/v1alpha/projects/{project_id}/locations/{location}/"
            f"collections/default_collection/engines/{engine_id}/assistants/default_assistant"
        )

    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        creds, _ = google.auth.default(quota_project_id=self.project_id)
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        return {
            "Authorization": f"Bearer {creds.token}",
            "X-Goog-User-Project": self.project_id,
            "Content-Type": "application/json"
        }

    def _create_authorization(self) -> Optional[str]:
        """
        Create OAuth authorization resource for BigQuery access.

        Returns:
            Authorization resource name, or None if OAuth credentials not configured
        """
        client_id = os.getenv("OAUTH_CLIENT_ID")
        client_secret = os.getenv("OAUTH_SECRET")

        if not client_id or not client_secret:
            print("Warning: OAUTH_CLIENT_ID or OAUTH_SECRET not set. Skipping authorization.")
            print("Agent will require manual OAuth authorization before querying BigQuery.")
            return None

        auth_id = f"auth-{uuid.uuid4()}"
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

        parent = f"projects/{self.project_id}/locations/{self.location}"
        url = f"https://{self.host}/v1alpha/{parent}/authorizations?authorizationId={auth_id}"

        payload = {
            "name": f"{parent}/authorizations/{auth_id}",
            "serverSideOauth2": {
                "clientId": client_id,
                "clientSecret": client_secret,
                "authorizationUri": auth_uri,
                "tokenUri": token_uri
            }
        }

        print(f"Creating OAuth authorization resource: {auth_id}")
        resp = requests.post(url, headers=self._get_headers(), json=payload)

        if resp.status_code == 200:
            auth_name = resp.json()["name"]
            print(f"Authorization created: {auth_name}")
            return auth_name
        else:
            print(f"Failed to create authorization: {resp.status_code} - {resp.text}")
            return None

    def _delete_existing_agent(self, agent_name: str):
        """Delete an existing agent to prepare for fresh deployment."""
        url = f"https://{self.host}/v1alpha/{agent_name}"
        print(f"Deleting existing agent: {agent_name}...")

        resp = requests.delete(url, headers=self._get_headers())
        if resp.status_code == 200:
            print("Agent deleted successfully.")
            time.sleep(5)  # Wait for deletion to propagate
        else:
            print(f"Failed to delete agent: {resp.status_code} - {resp.text}")

    def _wait_for_lro(self, operation_name: str, timeout: int = 300):
        """
        Wait for a Long-Running Operation (LRO) to complete.

        Args:
            operation_name: Full operation resource name
            timeout: Maximum wait time in seconds
        """
        url = f"https://{self.host}/v1alpha/{operation_name}"
        start_time = time.time()

        print(f"Waiting for LRO: {operation_name.split('/')[-1]}...")

        while time.time() - start_time < timeout:
            resp = requests.get(url, headers=self._get_headers())
            if resp.status_code != 200:
                print(f"LRO check failed: {resp.status_code}")
                return

            data = resp.json()
            if data.get("done", False):
                print("LRO completed successfully.")
                return

            time.sleep(5)

        print(f"LRO timed out after {timeout}s")

    def deploy_initial(self, config: Dict[str, Any]) -> str:
        """
        Deploy agent or reuse existing one.

        Steps:
        1. Check if agent exists
        2. If exists, reuse it (skip deployment, just store IDs)
        3. If doesn't exist, create and deploy new agent
        4. Store agent_id for future updates

        Args:
            config: Agent configuration dict with keys:
                - name: Config variant name (e.g., "baseline")
                - nl2sql_prompt: Base NL2SQL prompt
                - params: Optional params (schema_context, examples, etc.)
                - description: Agent description

        Returns:
            agent_id: The deployed agent ID
        """
        config_name = config.get("name", "baseline")
        self.agent_display_name = f"Data Agent - {config_name}"

        print(f"\nChecking for existing agent: {self.agent_display_name}")

        # 1. Check for existing agent
        agents_url = f"{self.base_url}/agents"
        resp = requests.get(agents_url, headers=self._get_headers())

        if resp.status_code == 200:
            agents = resp.json().get("agents", [])
            for agent in agents:
                if agent.get("displayName") == self.agent_display_name:
                    # Agent exists - reuse it
                    self.agent_name = agent["name"]
                    self.agent_id = self.agent_name.split("/")[-1]
                    print(f"✓ Found existing agent: {self.agent_display_name}")
                    print(f"  Agent ID: {self.agent_id}")
                    print(f"  Reusing existing agent (preserves OAuth authorization)")
                    return self.agent_id

        # Agent doesn't exist - create it
        print(f"Agent not found. Creating new agent: {self.agent_display_name}")

        # 2. Prepare prompt
        nl2sql_prompt = config.get("nl2sql_prompt", "")
        params = config.get("params", {})

        # Append schema context if present
        if "schema_context" in params:
            nl2sql_prompt += "\n\nSchema Context:\n" + params["schema_context"]

        # Append examples if present
        if "examples" in params and params["examples"]:
            examples_str = "\n".join(params["examples"])
            nl2sql_prompt += f"\n\nExamples:\n{examples_str}"

        # 3. Create OAuth authorization
        auth_resource = self._create_authorization()

        # 4. Create agent
        print(f"Creating agent '{self.agent_display_name}'...")

        payload = {
            "displayName": self.agent_display_name,
            "description": config.get("description", "Data Insights Agent for iterative optimization"),
            "managed_agent_definition": {
                "tool_settings": {
                    "tool_description": "Use this agent to query BigQuery data."
                },
                "data_science_agent_config": {
                    "bq_project_id": self.project_id,
                    "bq_dataset_id": self.dataset_id,
                    "nl_query_config": {
                        "nl2sqlPrompt": nl2sql_prompt
                    }
                }
            }
        }

        if auth_resource:
            payload["authorization_config"] = {
                "tool_authorizations": [auth_resource]
            }

        resp = requests.post(agents_url, headers=self._get_headers(), json=payload)

        if resp.status_code != 200:
            raise Exception(f"Failed to create agent: {resp.status_code} - {resp.text}")

        new_agent = resp.json()
        self.agent_name = new_agent["name"]
        self.agent_id = self.agent_name.split("/")[-1]

        print(f"Agent created successfully!")
        print(f"Agent ID: {self.agent_id}")
        print(f"Full Name: {self.agent_name}")

        # 5. Deploy agent
        print(f"Deploying agent...")
        deploy_url = f"https://{self.host}/v1alpha/{self.agent_name}:deploy"
        deploy_resp = requests.post(deploy_url, headers=self._get_headers(), json={"name": self.agent_name})

        if deploy_resp.status_code == 200:
            lro = deploy_resp.json()
            operation_name = lro.get('name')
            print(f"Deployment LRO started: {operation_name}")
            # Wait for deployment to complete before using agent
            self._wait_for_lro(operation_name)
        elif deploy_resp.status_code == 400 and "Invalid agent state for deploy: ENABLED" in deploy_resp.text:
            print("Agent already enabled.")
        else:
            print(f"Warning: Deploy request returned {deploy_resp.status_code} - {deploy_resp.text}")

        return self.agent_id

    def update_prompt(self, new_prompt: str, params: Dict[str, Any] = None) -> bool:
        """
        Update agent prompt using PATCH API.

        Preserves OAuth authorization and agent state while updating configuration.

        Args:
            new_prompt: New NL2SQL prompt text
            params: Optional params (schema_context, etc.)

        Returns:
            bool: True if update successful, False otherwise
        """
        if not self.agent_name:
            raise ValueError("Agent not deployed. Call deploy_initial() first.")

        print(f"\nUpdating agent prompt via PATCH API...")

        # Prepare nl_query_config
        nl_query_config = {
            "nl2sqlPrompt": new_prompt
        }

        if params and "schema_context" in params:
            nl_query_config["schemaDescription"] = params["schema_context"]

        payload = {
            "managed_agent_definition": {
                "data_science_agent_config": {
                    "bq_project_id": self.project_id,
                    "bq_dataset_id": self.dataset_id,
                    "nl_query_config": nl_query_config
                }
            }
        }

        # PATCH with update mask
        update_mask = "managedAgentDefinition.dataScienceAgentConfig.nlQueryConfig"
        url = f"https://{self.host}/v1alpha/{self.agent_name}?updateMask={update_mask}"

        resp = requests.patch(url, headers=self._get_headers(), json=payload)

        if resp.status_code != 200:
            print(f"PATCH failed: {resp.status_code} - {resp.text}")
            return False

        print("Agent prompt updated successfully!")

        # Check if LRO was returned
        data = resp.json()
        if "name" in data and "operations" in data["name"]:
            self._wait_for_lro(data["name"])

        return True

    def get_agent_id(self) -> Optional[str]:
        """Get the deployed agent ID."""
        return self.agent_id

    def get_agent_name(self) -> Optional[str]:
        """Get the full agent resource name."""
        return self.agent_name
