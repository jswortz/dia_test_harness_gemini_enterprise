from abc import ABC, abstractmethod
import time
import uuid
import requests
import os

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
        
        host = "discoveryengine.googleapis.com"
        if location != "global":
            host = f"{location}-discoveryengine.googleapis.com"
            
        self.base_url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}"
        self.engine_id = engine_id
        
        import google.auth
        import google.auth.transport.requests
        from google.oauth2 import service_account
        
        self.credentials, self.project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.auth_req = google.auth.transport.requests.Request()
        
    def _get_headers(self):
        self.credentials.refresh(self.auth_req)
        return {
            "Authorization": f"Bearer {self.credentials.token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": self.project_id
        }

    def create_agent(self, config: dict) -> str:
        # For DIA, the "Agent" is the Engine itself.
        # We reuse the existing Engine ID.
        return self.engine_id

    def delete_agent(self, agent_id: str) -> None:
        pass

    def ask_question(self, agent_id: str, question: str) -> dict:
        # Use v1beta sessions and :answer endpoint
        host = self.base_url.split("/v1alpha")[0]  # Hack to get clean host
        base_beta = f"{host}/v1beta/projects/{self.project_id}/locations/{self.location}/collections/default_collection/engines/{self.engine_id}"
        
        # 1. Create Session
        session_url = f"{base_beta}/sessions"
        session_payload = {"user_pseudo_id": f"user-{uuid.uuid4()}"}
        
        start = time.time()
        try:
            # Create Session
            sess_resp = requests.post(session_url, headers=self._get_headers(), json=session_payload)
            if sess_resp.status_code != 200:
                print(f"Session creation failed: {sess_resp.text}")
                return {"sql": f"Error: Session {sess_resp.status_code}", "result_data": [], "latency": 0}
            
            session_name = sess_resp.json()["name"]
            
            # 2. Answer
            answer_url = f"{base_beta}/servingConfigs/default_search:answer"
            payload = {
                "query": {"text": question},
                "session": session_name
            }
            
            # Print Payload for debug
            print(f"[RealAgentClient] Asking: {question}")
            
            resp = requests.post(answer_url, headers=self._get_headers(), json=payload)
            end = time.time()
            
            if resp.status_code == 200:
                data = resp.json()
                # Parse answer
                ans_text = data.get("answer", {}).get("answerText", "No answer text provided.")
                # We put the text in SQL field for now since we don't have SQL structure from Search response
                return {
                    "sql": ans_text, 
                    "result_data": [],
                    "latency": end - start
                }
            else:
                print(f"Answer failed: {resp.text}")
                return {"sql": f"Error: {resp.status_code}", "result_data": [], "latency": end - start}
                
        except Exception as e:
            print(f"Exception calling agent: {e}")
            return {"sql": f"Exception: {e}", "result_data": [], "latency": 0}


