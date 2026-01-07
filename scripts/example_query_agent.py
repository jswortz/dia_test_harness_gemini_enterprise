#!/usr/bin/env python3
"""
Example script showing the CORRECT way to query a Data Insights Agent.

CRITICAL: Must include agentsSpec to route to the Data Insights Agent.
Without it, queries go to the default assistant (no BigQuery access).
"""

import os
import sys
import json
from dotenv import load_dotenv

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.evaluation.agent_client import AgentClient

load_dotenv()


def main():
    # Required environment variables
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("AGENT_ID")  # The specific Data Insights Agent ID

    if not all([project_id, location, engine_id, agent_id]):
        print("ERROR: Missing required environment variables:")
        print(f"  GOOGLE_CLOUD_PROJECT: {project_id}")
        print(f"  DIA_LOCATION: {location}")
        print(f"  DIA_ENGINE_ID: {engine_id}")
        print(f"  AGENT_ID: {agent_id}")
        print("\nSet AGENT_ID to the ID of your Data Insights Agent")
        print("You can find it by inspecting the agent resource name:")
        print("  projects/.../engines/.../assistants/.../agents/{AGENT_ID}")
        sys.exit(1)

    # Initialize client
    client = AgentClient(
        project_id=project_id,
        location=location,
        engine_id=engine_id,
        agent_id=agent_id
    )

    # Example query
    question = "What are the top 5 customers by total order amount?"

    print(f"\n{'='*60}")
    print(f"Querying Data Insights Agent: {agent_id}")
    print(f"Question: {question}")
    print(f"{'='*60}\n")

    # Query the agent (agentsSpec is automatically included by the client)
    response = client.query_agent(question)

    # Display the raw response structure
    print("Raw Response Structure:")
    print(json.dumps(response, indent=2))
    print(f"\n{'='*60}\n")

    # Parse the response to extract thoughts and answer
    thoughts = []
    answer_parts = []
    session_id = None

    for chunk in response:
        # Extract thoughts and answers
        if 'answer' in chunk:
            for reply in chunk['answer'].get('replies', []):
                content = reply.get('groundedContent', {}).get('content', {})
                text = content.get('text', '')
                is_thought = content.get('thought', False)

                if is_thought:
                    thoughts.append(text)
                else:
                    answer_parts.append(text)

        # Extract session ID for follow-up queries
        if 'sessionInfo' in chunk:
            session_id = chunk['sessionInfo'].get('session')

    # Display parsed results
    if thoughts:
        print("Agent Thoughts (Internal Reasoning):")
        print("".join(thoughts))
        print(f"\n{'='*60}\n")

    if answer_parts:
        print("Agent Answer:")
        print("".join(answer_parts))
        print(f"\n{'='*60}\n")

    # Optional: Follow-up question using the session
    if session_id:
        print(f"Session ID: {session_id}\n")
        followup = "What was the SQL query used for the previous answer?"
        print(f"Follow-up question: {followup}\n")

        followup_response = client.query_agent(followup, session_id=session_id)

        for chunk in followup_response:
            if 'answer' in chunk:
                for reply in chunk['answer'].get('replies', []):
                    content = reply.get('groundedContent', {}).get('content', {})
                    text = content.get('text', '')
                    if text and not content.get('thought', False):
                        print(f"SQL Query:\n{text}")


if __name__ == "__main__":
    main()
