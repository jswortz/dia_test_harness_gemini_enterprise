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
import logging
import json
from typing import Dict, Any, Optional
from urllib.parse import quote


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

    def _wait_for_lro(self, operation_name: str, timeout: int = None):
        """
        Wait for a Long-Running Operation (LRO) to complete with exponential backoff.

        Args:
            operation_name: Full operation resource name
            timeout: Maximum wait time in seconds (default: from env DIA_LRO_TIMEOUT or 600s)
        """
        # Get timeout from environment variable or use default
        if timeout is None:
            timeout = int(os.getenv("DIA_LRO_TIMEOUT", "600"))

        # Enforce reasonable bounds (minimum 60s, maximum 3600s = 1 hour)
        timeout = max(60, min(timeout, 3600))
        url = f"https://{self.host}/v1alpha/{operation_name}"
        start_time = time.time()

        print(f"Waiting for LRO: {operation_name.split('/')[-1]}...")
        print(f"  Max timeout: {timeout}s ({timeout//60}m)")

        checks = 0
        poll_interval = 5  # Start with 5 second polling
        max_poll_interval = 30  # Cap at 30 seconds

        while time.time() - start_time < timeout:
            resp = requests.get(url, headers=self._get_headers())
            if resp.status_code != 200:
                print(f"LRO check failed: {resp.status_code} - {resp.text[:200]}")
                # Don't fail immediately - the operation might still complete
                time.sleep(poll_interval)
                checks += 1
                continue

            data = resp.json()

            # Check for errors in the LRO
            if "error" in data:
                print(f"LRO failed with error: {data['error']}")
                return False

            if data.get("done", False):
                elapsed = int(time.time() - start_time)
                # Check if there's a result or error in the response
                if "error" in data:
                    print(f"LRO completed with error after {elapsed}s: {data['error']}")
                    return False
                elif "response" in data:
                    print(f"✓ LRO completed successfully ({elapsed}s)")
                    return True
                else:
                    print(f"✓ LRO completed ({elapsed}s)")
                    return True

            checks += 1
            elapsed = int(time.time() - start_time)

            # Check if agent is actually deployed every 3 checks (even if LRO not done)
            # This prevents unnecessary polling when agent is ready but LRO hasn't marked done=true
            if checks % 3 == 0:
                if self._verify_agent_deployed():
                    print(f"✓ Agent is deployed and ready ({elapsed}s) - exiting early")
                    return True

            # Print progress every 3 checks or every 30s, whichever comes first
            if checks % 3 == 0 or elapsed % 30 < poll_interval:
                remaining = timeout - elapsed
                print(f"  ⏳ Still waiting... {elapsed}s elapsed, {remaining}s remaining")

            # Exponential backoff: gradually increase poll interval
            # Start at 5s, increase to 10s after 60s, 20s after 120s, cap at 30s
            if elapsed > 120 and poll_interval < 20:
                poll_interval = 20
                print(f"  Increasing poll interval to {poll_interval}s")
            elif elapsed > 60 and poll_interval < 10:
                poll_interval = 10
                print(f"  Increasing poll interval to {poll_interval}s")

            time.sleep(poll_interval)

        print(f"\n⚠️  LRO timed out after {timeout}s")
        print("Checking if agent is actually deployed...")

        # Verify agent is deployed by checking its state
        if self._verify_agent_deployed():
            print("✓ Agent is deployed and ready (LRO timeout ignored)")
            return True
        else:
            print("✗ Agent deployment could not be verified")
            return False

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

        # 2. Prepare configuration with all API fields
        nl2sql_prompt = config.get("nl2sql_prompt", "")
        params = config.get("params", {})

        # Build nl_query_config with all available fields
        nl_query_config = {
            "nl2sqlPrompt": nl2sql_prompt
        }

        # Add schema description if present
        if config.get("schema_description"):
            nl_query_config["schemaDescription"] = config["schema_description"]

        # Add Python prompt if present
        if config.get("nl2py_prompt"):
            nl_query_config["nl2pyPrompt"] = config["nl2py_prompt"]

        # Add few-shot examples if present
        if config.get("nl2sql_examples"):
            nl_query_config["nl2sqlExamples"] = config["nl2sql_examples"]

        # Legacy: Append schema context from params if present
        if "schema_context" in params:
            if "schemaDescription" in nl_query_config:
                nl_query_config["schemaDescription"] += "\n\n" + params["schema_context"]
            else:
                nl_query_config["schemaDescription"] = params["schema_context"]

        # Legacy: Append examples from params if present
        if "examples" in params and params["examples"]:
            examples_str = "\n".join(params["examples"])
            nl_query_config["nl2sqlPrompt"] += f"\n\nExamples:\n{examples_str}"

        # 3. Create OAuth authorization
        auth_resource = self._create_authorization()

        # 4. Create agent with comprehensive configuration
        print(f"Creating agent '{self.agent_display_name}'...")

        payload = {
            "displayName": config.get("display_name", self.agent_display_name),
            "description": config.get("description", "Data Insights Agent for iterative optimization"),
            "managed_agent_definition": {
                "tool_settings": {
                    "tool_description": config.get("tool_description", "Use this agent to query BigQuery data.")
                },
                "data_science_agent_config": {
                    "bq_project_id": self.project_id,
                    "bq_dataset_id": self.dataset_id,
                    "nl_query_config": nl_query_config
                }
            }
        }

        # Add icon if present
        if config.get("icon_uri"):
            payload["icon"] = {"uri": config["icon_uri"]}

        # NOTE: Table access control fields (allowedTables, blockedTables) are not supported by the API
        # Commenting out to prevent API errors
        # data_science_config = payload["managed_agent_definition"]["data_science_agent_config"]
        # if config.get("allowed_tables"):
        #     data_science_config["allowedTables"] = config["allowed_tables"]
        # if config.get("blocked_tables"):
        #     data_science_config["blockedTables"] = config["blocked_tables"]

        # Add authorization config if OAuth resource created
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
            resp_data = deploy_resp.json()

            # Check if response contains an LRO operation
            if 'name' in resp_data and 'operations' in resp_data['name']:
                operation_name = resp_data['name']
                print(f"Deployment LRO started: {operation_name}")
                # Wait for deployment to complete before using agent (10 minute timeout)
                lro_success = self._wait_for_lro(operation_name, timeout=600)
                if lro_success:
                    print("✓ Agent deployed and ready!")
                else:
                    print("⚠️  Deployment verification inconclusive - check console")
            else:
                # Direct success response (no LRO needed)
                print("✓ Agent deployed successfully (no LRO wait needed).")
        elif deploy_resp.status_code == 400 and "Invalid agent state for deploy: ENABLED" in deploy_resp.text:
            print("✓ Agent already enabled.")
        else:
            print(f"Warning: Deploy request returned {deploy_resp.status_code} - {deploy_resp.text[:300]}")

        return self.agent_id

    def update_prompt(self, new_prompt: str, params: Dict[str, Any] = None, full_config: Dict[str, Any] = None) -> bool:
        """
        Update agent configuration using PATCH API with retry logic.

        Preserves OAuth authorization and agent state while updating configuration.

        Args:
            new_prompt: New NL2SQL prompt text
            params: Optional params (schema_context, etc.) - legacy support
            full_config: Optional full configuration dict with all fields

        Returns:
            bool: True if update successful, False otherwise
        """
        if not self.agent_name:
            raise ValueError("Agent not deployed. Call deploy_initial() first.")

        max_retries = 3
        current_retry_delay = 5  # Initial delay in seconds

        for attempt in range(1, max_retries + 1):
            try:
                print(f"\n{'─'*80}")
                print(f"Updating agent configuration (attempt {attempt}/{max_retries})")
                print(f"{'─'*80}")

                # Build nl_query_config with all fields
                nl_query_config = {
                    "nl2sqlPrompt": new_prompt
                }

                # If full_config provided, use all its fields (skip null/empty values)
                if full_config:
                    # Only add schema_description if it's non-null and non-empty
                    if full_config.get("schema_description"):
                        nl_query_config["schemaDescription"] = full_config["schema_description"]

                    # Only add nl2py_prompt if it's non-null and non-empty
                    nl2py = full_config.get("nl2py_prompt")
                    if nl2py and nl2py is not None:
                        nl_query_config["nl2pyPrompt"] = nl2py

                    # Only add nl2sql_examples if it's a non-empty list
                    examples = full_config.get("nl2sql_examples")
                    if examples and isinstance(examples, list) and len(examples) > 0:
                        nl_query_config["nl2sqlExamples"] = examples

                # Legacy: support params dict
                if params and "schema_context" in params:
                    nl_query_config["schemaDescription"] = params["schema_context"]

                # Build minimal payload - only include nlQueryConfig for update
                # (bq_project_id and bq_dataset_id are immutable after creation)
                payload = {
                    "managed_agent_definition": {
                        "data_science_agent_config": {
                            "nl_query_config": nl_query_config
                        }
                    }
                }

                # Only update nlQueryConfig fields during optimization
                # Table access control (allowed_tables/blocked_tables) should remain static
                update_mask_fields = ["managedAgentDefinition.dataScienceAgentConfig.nlQueryConfig"]

                # PATCH with update mask (URL-encoded)
                update_mask = ",".join(update_mask_fields)
                encoded_mask = quote(update_mask, safe='')
                url = f"https://{self.host}/v1alpha/{self.agent_name}?updateMask={encoded_mask}"

                print(f"Update mask: {update_mask}")

                print("Sending PATCH request...")
                resp = requests.patch(url, headers=self._get_headers(), json=payload)

                if resp.status_code != 200:
                    error_msg = f"PATCH failed: {resp.status_code}"
                    print(f"\n❌ {error_msg}")
                    print(f"\n📋 Full Error Response:")
                    print(f"{resp.text}")  # Show full error
                    print(f"\n📤 Request Details:")
                    print(f"URL: {url}")
                    print(f"Update Mask: {update_mask}")
                    print(f"\n📦 Payload (first 1000 chars):")
                    print(f"{json.dumps(payload, indent=2)[:1000]}")

                    # Log detailed error
                    logging.error(f"PATCH attempt {attempt} failed")
                    logging.error(f"URL: {url}")
                    logging.error(f"Payload: {json.dumps(payload, indent=2)}")
                    logging.error(f"Response: {resp.text}")

                    if attempt < max_retries:
                        print(f"Retrying in {current_retry_delay}s...")
                        time.sleep(current_retry_delay)
                        current_retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        return False

                print("✓ PATCH successful")

                # Check if LRO was returned from PATCH
                data = resp.json()
                if "name" in data and "operations" in data["name"]:
                    print("PATCH returned LRO - waiting for completion...")
                    self._wait_for_lro(data["name"], timeout=600)

                # Deploy the agent to enable it after configuration update
                print("\n🚀 Deploying updated agent...")
                deploy_success = self._deploy_agent()

                if not deploy_success:
                    if attempt < max_retries:
                        print(f"❌ Deploy failed. Retrying in {current_retry_delay}s...")
                        time.sleep(current_retry_delay)
                        current_retry_delay *= 2
                        continue
                    else:
                        return False

                print("✅ Agent deployed and ready!")

                # Verify the config was actually updated
                if full_config:
                    print("\n🔍 Verifying configuration was applied...")
                    if self._verify_config_update(full_config):
                        print("✓ Configuration verified - changes applied successfully")
                    else:
                        print("⚠️  Warning: Configuration verification inconclusive")
                        print("   The PATCH succeeded, but couldn't verify all fields were updated")

                return True

            except Exception as e:
                error_msg = f"Exception during update: {e}"
                print(f"❌ {error_msg}")
                logging.error(error_msg)

                if attempt < max_retries:
                    print(f"Retrying in {current_retry_delay}s...")
                    time.sleep(current_retry_delay)
                    current_retry_delay *= 2
                    continue
                else:
                    return False

        return False

    def _verify_agent_deployed(self) -> bool:
        """
        Verify that the agent is actually deployed and ready.

        Returns:
            bool: True if agent is deployed and enabled, False otherwise
        """
        if not self.agent_name:
            return False

        try:
            # Get agent details
            url = f"https://{self.host}/v1alpha/{self.agent_name}"
            resp = requests.get(url, headers=self._get_headers())

            if resp.status_code == 200:
                agent_data = resp.json()
                state = agent_data.get("state", "UNKNOWN")
                print(f"  Agent state: {state}")
                # Accept both ENABLED and ACTIVE as valid deployed states
                return state in ["ENABLED", "ACTIVE"]
            else:
                print(f"  Failed to get agent status: {resp.status_code}")
                return False
        except Exception as e:
            print(f"  Error verifying agent: {e}")
            return False

    def _verify_config_update(self, expected_config: Dict[str, Any]) -> bool:
        """
        Verify that the agent's configuration matches the expected configuration.

        Args:
            expected_config: The configuration that should have been applied

        Returns:
            bool: True if verification succeeds, False otherwise
        """
        if not self.agent_name:
            return False

        try:
            # Fetch current agent config
            url = f"https://{self.host}/v1alpha/{self.agent_name}"
            resp = requests.get(url, headers=self._get_headers())

            if resp.status_code != 200:
                print(f"  Failed to fetch agent for verification: {resp.status_code}")
                return False

            agent_data = resp.json()
            managed_def = agent_data.get("managedAgentDefinition", {})
            data_science_config = managed_def.get("dataScienceAgentConfig", {})
            nl_query_config = data_science_config.get("nlQueryConfig", {})

            # Verify key fields
            verifications = []

            # Check prompt (most critical field)
            expected_prompt = expected_config.get("nl2sql_prompt", "")
            actual_prompt = nl_query_config.get("nl2sqlPrompt", "")
            prompt_match = len(actual_prompt) == len(expected_prompt)
            verifications.append(("nl2sql_prompt", prompt_match))
            if not prompt_match:
                print(f"  ⚠️  Prompt length mismatch: expected {len(expected_prompt)}, got {len(actual_prompt)}")

            # Check schema description if provided
            if expected_config.get("schema_description"):
                expected_schema = expected_config["schema_description"]
                actual_schema = nl_query_config.get("schemaDescription", "")
                schema_match = len(actual_schema) == len(expected_schema)
                verifications.append(("schema_description", schema_match))
                if not schema_match:
                    print(f"  ⚠️  Schema description length mismatch: expected {len(expected_schema)}, got {len(actual_schema)}")

            # Check examples if provided
            if expected_config.get("nl2sql_examples"):
                expected_examples = expected_config["nl2sql_examples"]
                actual_examples = nl_query_config.get("nl2sqlExamples", [])
                examples_match = len(actual_examples) == len(expected_examples)
                verifications.append(("nl2sql_examples", examples_match))
                if not examples_match:
                    print(f"  ⚠️  Examples count mismatch: expected {len(expected_examples)}, got {len(actual_examples)}")

            # Overall verification
            all_verified = all(match for _, match in verifications)
            verified_count = sum(1 for _, match in verifications if match)

            print(f"  Verified {verified_count}/{len(verifications)} config fields")
            return all_verified

        except Exception as e:
            print(f"  Error during config verification: {e}")
            return False

    def _deploy_agent(self) -> bool:
        """
        Deploy the agent (helper method for retry logic).

        Returns:
            bool: True if deployment successful, False otherwise
        """
        # First check if agent is already deployed/enabled
        if self._verify_agent_deployed():
            print("✓ Agent already deployed and enabled (skipping deploy call)")
            return True

        deploy_url = f"https://{self.host}/v1alpha/{self.agent_name}:deploy"
        deploy_payload = {"name": self.agent_name}

        deploy_resp = requests.post(deploy_url, headers=self._get_headers(), json=deploy_payload)

        if deploy_resp.status_code == 200:
            resp_data = deploy_resp.json()

            # Check if response contains an LRO operation
            if 'name' in resp_data and 'operations' in resp_data['name']:
                operation_name = resp_data['name']
                print(f"Deployment LRO started: {operation_name}")
                lro_success = self._wait_for_lro(operation_name, timeout=600)
                if lro_success:
                    print("✓ Deployment LRO completed")
                    return True
                else:
                    # LRO failed or timed out - final verification already done in _wait_for_lro
                    return False
            else:
                # Direct success response (no LRO needed)
                print("✓ Agent deployed (no LRO wait needed)")
            return True
        elif deploy_resp.status_code == 400 and "Invalid agent state for deploy: ENABLED" in deploy_resp.text:
            print("✓ Agent already enabled")
            return True
        else:
            print(f"Deploy failed: {deploy_resp.status_code} - {deploy_resp.text[:300]}")
            logging.error(f"Deploy failed: {deploy_resp.status_code} - {deploy_resp.text}")
            return False

    def find_existing_agent(self, display_name: str) -> Optional[str]:
        """
        Find an existing agent by display name (no deployment).

        Args:
            display_name: Display name to search for (e.g., "Data Agent - baseline")

        Returns:
            agent_id if found, None otherwise
        """
        print(f"Searching for existing agent: {display_name}")

        agents_url = f"{self.base_url}/agents"
        resp = requests.get(agents_url, headers=self._get_headers())

        if resp.status_code != 200:
            print(f"Failed to list agents: {resp.status_code} - {resp.text}")
            return None

        agents = resp.json().get("agents", [])
        for agent in agents:
            if agent.get("displayName") == display_name:
                # Found matching agent
                self.agent_name = agent["name"]
                self.agent_id = self.agent_name.split("/")[-1]
                self.agent_display_name = display_name
                print(f"✓ Found existing agent: {display_name}")
                print(f"  Agent ID: {self.agent_id}")
                print(f"  Full Name: {self.agent_name}")
                return self.agent_id

        print(f"✗ Agent not found: {display_name}")
        print(f"  Please run 'dia-harness deploy' first to create the agent.")
        return None

    def get_agent_id(self) -> Optional[str]:
        """Get the deployed agent ID."""
        return self.agent_id

    def get_agent_name(self) -> Optional[str]:
        """Get the full agent resource name."""
        return self.agent_name

    def get_agent_config(self) -> Optional[Dict[str, Any]]:
        """
        Fetch the current configuration of the deployed agent from the API.

        Returns:
            Dictionary with agent configuration fields, or None if fetch fails
        """
        if not self.agent_name:
            logging.error("No agent deployed yet. Call deploy_initial() or find_existing_agent() first.")
            return None

        print(f"\n📥 Fetching current config from deployed agent...")
        agent_url = f"https://{self.host}/v1alpha/{self.agent_name}"

        try:
            resp = requests.get(agent_url, headers=self._get_headers())

            if resp.status_code != 200:
                logging.error(f"Failed to get agent config: {resp.status_code} - {resp.text[:500]}")
                print(f"✗ Failed to fetch agent config: {resp.status_code}")
                return None

            agent_data = resp.json()

            # Extract relevant config fields from the API response
            # The API returns fields in camelCase format
            managed_def = agent_data.get("managedAgentDefinition", {})
            data_science_config = managed_def.get("dataScienceAgentConfig", {})
            nl_query_config = data_science_config.get("nlQueryConfig", {})
            tool_settings = managed_def.get("toolSettings", {})

            # Extract config name from display name (e.g., "Data Agent - baseline" -> "baseline")
            display_name = agent_data.get("displayName", "")
            config_name = display_name.split(" - ")[-1] if " - " in display_name else "baseline"

            config = {
                "name": config_name,
                "display_name": display_name,
                "description": agent_data.get("description", ""),
                "nl2sql_prompt": nl_query_config.get("nl2sqlPrompt", ""),
                "nl2py_prompt": nl_query_config.get("nl2pyPrompt"),
                "tool_description": tool_settings.get("toolDescription", ""),
                "schema_description": nl_query_config.get("schemaDescription", ""),
                "nl2sql_examples": nl_query_config.get("nl2sqlExamples", []),
                "bq_project_id": data_science_config.get("bqProjectId", self.project_id),
                "bq_dataset_id": data_science_config.get("bqDatasetId", self.dataset_id),
                # Note: allowedTables and blockedTables are not supported by API
                "params": {}  # Legacy field for backward compatibility
            }

            print(f"✓ Fetched config from deployed agent")
            logging.info(f"Retrieved agent config: name={config['name']}, "
                        f"nl2sql_prompt={len(config['nl2sql_prompt'])} chars, "
                        f"examples={len(config.get('nl2sql_examples', []))}")

            return config

        except Exception as e:
            logging.error(f"Error fetching agent config: {e}", exc_info=True)
            print(f"✗ Error fetching agent config: {e}")
            return None
