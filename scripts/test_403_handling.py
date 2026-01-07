#!/usr/bin/env python3
"""
Test script to verify 403 authorization error handling.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.evaluation.agent_client import AgentClient, AgentAuthorizationError

# Test with a fake/unauthorized agent ID
project_id = "wortz-project-352116"
location = "global"
engine_id = "gemini-enterprise-17634901_1763490144996"
fake_agent_id = "99999999999999999"  # Non-existent agent

print("Testing 403 authorization error handling...\n")
print(f"Using fake agent ID: {fake_agent_id}")
print("This should trigger a 403 error and raise AgentAuthorizationError\n")

try:
    client = AgentClient(project_id, location, engine_id, fake_agent_id)
    response = client.query_agent("How many customers are there?")
    print("Query succeeded - checking response...")
    print(f"Response: {response}")
except AgentAuthorizationError as e:
    print("✅ SUCCESS: AgentAuthorizationError was raised correctly!")
    print(f"\nError details:")
    print(f"  Agent ID: {e.agent_id}")
    print(f"  Project: {e.project_id}")
    print(f"  Location: {e.location}")
    print(f"  Engine: {e.engine_id}")
    print(f"\nMessage: {e}")
except Exception as e:
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {e}")
    import traceback
    traceback.print_exc()
