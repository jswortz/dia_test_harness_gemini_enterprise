#!/usr/bin/env python3
"""Debug script to see the full agent response."""

import os
import sys
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.evaluation.agent_client import AgentClient

load_dotenv()

def main():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")

    print(f"Testing agent: {agent_id}\n")

    client = AgentClient(project_id, location, engine_id, agent_id)

    question = "How many customers are there?"
    print(f"Question: {question}\n")

    response = client.query_agent(question)

    print("="*60)
    print("FULL RAW RESPONSE")
    print("="*60)
    print(json.dumps(response, indent=2))
    print("\n" + "="*60)
    print("PARSED CONTENT")
    print("="*60 + "\n")

    for i, chunk in enumerate(response):
        print(f"--- Chunk {i+1} ---")

        if 'answer' in chunk:
            state = chunk['answer'].get('state', 'UNKNOWN')
            print(f"State: {state}")

            for reply in chunk['answer'].get('replies', []):
                content = reply.get('groundedContent', {}).get('content', {})
                text = content.get('text', '')
                is_thought = content.get('thought', False)

                content_type = "THOUGHT" if is_thought else "ANSWER"
                print(f"  [{content_type}]: {text[:200]}{'...' if len(text) > 200 else ''}")

        if 'sessionInfo' in chunk:
            print(f"Session: {chunk['sessionInfo'].get('session', 'N/A')}")

        print()

if __name__ == "__main__":
    main()
