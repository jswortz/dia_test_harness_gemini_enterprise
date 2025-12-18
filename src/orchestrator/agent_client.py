from abc import ABC, abstractmethod
import time
import uuid
import requests
import os
from typing import Dict, Any, List

class AgentClient(ABC):
    """Abstract base class for interacting with DIA Agents."""
    
    @abstractmethod
    def create_agent(self, config: dict) -> str:
        """Deploys an agent and returns its ID."""
        pass

    @abstractmethod
    def delete_agent(self, agent_id: str) -> None:
        """Deletes an agent."""
        pass

    @abstractmethod
    def ask_question(self, agent_id: str, question: str) -> dict:
        """Asks a question to the agent and returns the response."""
        pass

class MockAgentClient(AgentClient):
    """Mock implementation for testing harness logic."""
    
    def __init__(self):
        self.active_agents = {}

    def create_agent(self, config: dict) -> str:
        agent_id = f"mock-agent-{uuid.uuid4()}"
        self.active_agents[agent_id] = config
        print(f"[Mock] Created agent {agent_id} with config: {config.get('name', 'unnamed')}")
        time.sleep(1) # Simulate deployment time
        return agent_id

    def delete_agent(self, agent_id: str) -> None:
        if agent_id in self.active_agents:
            del self.active_agents[agent_id]
            print(f"[Mock] Deleted agent {agent_id}")
        else:
            print(f"[Mock] Warning: Attempted to delete non-existent agent {agent_id}")

    def ask_question(self, agent_id: str, question: str) -> dict:
        """Returns a mock response dependent on the question complexity or keywords."""
        if agent_id not in self.active_agents:
            raise ValueError(f"Agent {agent_id} does not exist.")
            
        # Simulate processing time
        time.sleep(0.5) 
        
        # Simple keyword matching to simulate different responses
        # In a real scenario, this would call the Gemini API
        response = {
            "sql": f"SELECT * FROM mock_table WHERE query='{question}'",
            "result_data": [{"col": "val"}],
            "latency": 0.5
        }
        
        if "count" in question.lower():
            response["sql"] = "SELECT count(*) FROM table"
            response["result_data"] = [{"f0_": 42}]
        elif "list" in question.lower():
            response["sql"] = "SELECT name FROM products"
            response["result_data"] = [{"name": "Widget A"}, {"name": "Widget B"}]
            
        return response

class RealAgentClient(AgentClient):
    """Real implementation interacting with Google Cloud Discovery Engine."""

    def __init__(self, project_id: str = None, location: str = "global", engine_id: str = None):
        if not project_id:
             project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not engine_id:
             engine_id = os.getenv("DIA_ENGINE_ID")
        
        self.project_id = project_id
        self.location = location.lower()
        self.physical_engine_id = engine_id
        self.active_handles = {}  # Map handle_id -> {config, engine_id}

        import google.auth
        import google.auth.transport.requests
        
        self.credentials, self.project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.auth_req = google.auth.transport.requests.Request()
        
    def _get_headers(self):
        self.credentials.refresh(self.auth_req)
        return {
            "Authorization": f"Bearer {self.credentials.token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": self.project_id
        }

    def create_agent(self, config_name: str, config: Dict[str, Any] = None) -> str:
        """
        Configures the Persistent Engine's Agent (v1alpha) with the given config.
        Returns the engine_id (persistent).
        """
        engine_id = self.physical_engine_id
        print(f"[{config_name}] Configuring Persistent Engine: {engine_id}...")
        
        # 1. Get Default Agent
        agent_name = self._get_default_agent(engine_id)
        if not agent_name:
             print(f"[{config_name}] Error: No default agent found on persistent engine.")
             raise Exception("No default agent found on persistent engine")
             
        # 2. Patch Agent Config
        print(f"[{config_name}] Patching Agent {agent_name}...")
        display_name = self._patch_agent_config(agent_name, config)
        
        # Store handle
        self.active_handles[engine_id] = {
            "config": config,
            "engine_id": engine_id,
            "display_name": display_name
        }
        return engine_id

    def delete_agent(self, agent_handle: str):
        """Reverts or cleans up agent config. For persistent engine, we might reset to default."""
        if agent_handle == self.physical_engine_id:
            print(f"Skipping delete for persistent engine {agent_handle}")
            return

        # Fallback for dynamic engines (if any)
        print(f"Deleting Engine {agent_handle}...")
        host = "discoveryengine.googleapis.com"
        if self.location != "global":
            host = f"{self.location}-discoveryengine.googleapis.com"
            
        url = f"https://{host}/v1beta/projects/{self.project_id}/locations/{self.location}/collections/default_collection/engines/{agent_handle}"
        
        try:
            resp = requests.delete(url, headers=self._get_headers())
            if resp.status_code not in [200, 404]:
                print(f"Warning: Failed to delete engine {agent_handle}: {resp.text}")
            else:
                print(f"Deletion initiated for Engine {agent_handle}")
        except Exception as e:
            print(f"Error deleting engine {agent_handle}: {e}")
            
        if agent_handle in self.active_handles:
            del self.active_handles[agent_handle]

    def _get_default_agent(self, engine_id: str) -> str:
        """Finds the default agent name for the engine."""
        host = "discoveryengine.googleapis.com"
        if self.location != "global":
            host = f"{self.location}-discoveryengine.googleapis.com"
            
        parent = f"projects/{self.project_id}/locations/{self.location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant"
        url = f"https://{host}/v1alpha/{parent}/agents"
        
        try:
            resp = requests.get(url, headers=self._get_headers())
            if resp.status_code == 200:
                agents = resp.json().get("agents", [])
                if agents:
                    return agents[0]["name"]
        except Exception as e:
            print(f"Error listing agents: {e}")
        return None

    def _patch_agent_config(self, agent_name: str, config: Dict[str, Any]):
        """Patches the agent with dataScienceAgentConfig and Display Name."""
        host = "discoveryengine.googleapis.com"
        if self.location != "global":
            host = f"{self.location}-discoveryengine.googleapis.com"
            
        url = f"https://{host}/v1alpha/{agent_name}"
        
        # Prepare Config
        bq_project_id = config.get("bq_project_id", self.project_id)
        bq_dataset_id = config.get("bq_dataset_id", "dia_test_dataset")
        params = config.get("parameters", {})
        
        # Determine Display Name for @mention
        # Use a simple, space-free name to ensure easy parsing.
        display_name = f"TestAgent"
        
        nl_query_config = {}
        prompt = "You are a specialized Data Scientist agent."
        if "examples" in params and params["examples"]:
             examples_str = "\n".join(params["examples"])
             prompt += f"\n\nExamples:\n{examples_str}"
             
        if "schema_context" in params:
             nl_query_config["schemaDescription"] = params["schema_context"]
        
        nl_query_config["nl2sqlPrompt"] = prompt
        
        payload = {
            "displayName": display_name,
            "managed_agent_definition": {
                "data_science_agent_config": {
                    "bq_project_id": bq_project_id,
                    "bq_dataset_id": bq_dataset_id,
                    "nl_query_config": nl_query_config
                }
            }
        }
        
        # Patch and wait
        # Note: updateMask must include displayName
        params_qs = "updateMask=displayName,managedAgentDefinition.dataScienceAgentConfig"
        resp = requests.patch(f"{url}?{params_qs}", headers=self._get_headers(), json=payload)
        
        if resp.status_code != 200:
            print(f"Patch Config Failed: {resp.text}")
        else:
            print(f"Agent Config Patched. Renamed to '{display_name}'.")
            data = resp.json()
            if "name" in data and "operations" in data["name"]:
                 print("Waiting for Agent Patch LRO...")
                 self._wait_for_lro(data["name"], api_version="v1alpha")
                 
            # Store the display name in the active handle so ask_question can use it
            # We need to find the engine_id for this agent, which is passed in create_agent
            # But here we are inside _patch_agent_config.
            # We can rely on create_agent updating the handle map after this call.
            return display_name
            
    def ask_question(self, agent_handle: str, question: str) -> dict:
        """
        Asks a question to the Agent via the Engine's Serving Config (v1beta).
        Prepends @<AgentName> if available.
        """
        engine_to_use = agent_handle
        agent_display_name = "TestAgent" # Default
        
        if agent_handle in self.active_handles:
             handle_data = self.active_handles[agent_handle]
             if "engine_id" in handle_data:
                 engine_to_use = handle_data["engine_id"]
             # If we stored the display name
             if "display_name" in handle_data:
                 agent_display_name = handle_data["display_name"]
        
        # Prepend @mention
        routed_question = f"@{agent_display_name} {question}"
        print(f"Asking: {routed_question}")

        host = "discoveryengine.googleapis.com"
        if self.location != "global":
            host = f"{self.location}-discoveryengine.googleapis.com"
            
        # 1. Create Session
        session_url = f"https://{host}/v1beta/projects/{self.project_id}/locations/{self.location}/collections/default_collection/engines/{engine_to_use}/sessions"
        session_payload = {"userPseudoId": "test-user-123"} 
        
        start_time = time.time()
        try:
            sess_resp = requests.post(session_url, headers=self._get_headers(), json=session_payload)
            if sess_resp.status_code != 200:
                print(f"Session Create Failed: {sess_resp.text}")
                return {"sql": "", "answer": "Session Creation Failed"}
            session_name = sess_resp.json()["name"]
            
            # 2. Answer
            # Use Engine-level endpoint, pass session in payload
            answer_url = f"https://{host}/v1beta/projects/{self.project_id}/locations/{self.location}/collections/default_collection/engines/{engine_to_use}/servingConfigs/default_search:answer"
            
            payload = {
                "query": {"text": routed_question},
                "relatedQuestionsSpec": {"enable": False},
                "session": session_name
            }
            
            ans_resp = requests.post(answer_url, headers=self._get_headers(), json=payload)
            latency = time.time() - start_time
            
            if ans_resp.status_code != 200:
                print(f"Answer Failed: {ans_resp.text}")
                return {"sql": "", "answer": f"Error: {ans_resp.status_code}", "latency": latency}
                
            ans_data = ans_resp.json()
            answer_text = ans_data.get("answer", {}).get("answerText", "")
            
            return {"sql": answer_text, "answer": answer_text, "latency": latency}
            
        except Exception as e:
            print(f"Ask Exception: {e}")
            return {"sql": f"Exception: {str(e)}", "answer": str(e), "latency": 0}
