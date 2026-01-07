#!/usr/bin/env python3
"""
Script to generate and display OAuth authorization URLs for Data Insights Agents.

When agents need BigQuery access, they require OAuth authorization. This script:
1. Sends a test query to the agent
2. Extracts the authorization URL from the response
3. Displays it for the user to visit and authorize
"""

import os
import sys
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.evaluation.agent_client import AgentClient

load_dotenv()


def extract_authorization_urls(response):
    """Extract all authorization URLs from the agent response."""
    auth_urls = []

    for chunk in response:
        if 'answer' in chunk:
            required_auths = chunk['answer'].get('requiredAuthorizations', [])
            for auth in required_auths:
                auth_info = {
                    'authorization': auth.get('authorization', 'N/A'),
                    'display_name': auth.get('displayName', 'N/A'),
                    'uri': auth.get('authorizationUri', '')
                }
                if auth_info['uri']:
                    auth_urls.append(auth_info)

    return auth_urls


def main():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")

    if not all([project_id, location, engine_id, agent_id]):
        print("ERROR: Missing required environment variables")
        print(f"  GOOGLE_CLOUD_PROJECT: {project_id or 'NOT SET'}")
        print(f"  DIA_LOCATION: {location or 'NOT SET'}")
        print(f"  DIA_ENGINE_ID: {engine_id or 'NOT SET'}")
        print(f"  DIA_AGENT_ID: {agent_id or 'NOT SET'}")
        sys.exit(1)

    print("="*70)
    print("DATA INSIGHTS AGENT - OAUTH AUTHORIZATION")
    print("="*70)
    print(f"\nProject: {project_id}")
    print(f"Location: {location}")
    print(f"Engine: {engine_id}")
    print(f"Agent ID: {agent_id}")
    print()

    # Initialize client
    client = AgentClient(project_id, location, engine_id, agent_id)

    # Send a test query that requires BigQuery access
    test_question = "How many customers are there?"
    print(f"Sending test query: '{test_question}'")
    print("This will trigger authorization requirements if not already authorized.\n")
    print("Querying agent...")

    try:
        response = client.query_agent(test_question)

        # Extract authorization URLs
        auth_urls = extract_authorization_urls(response)

        if auth_urls:
            print("\n" + "="*70)
            print("⚠️  AUTHORIZATION REQUIRED")
            print("="*70)
            print("\nYour Data Insights Agent needs authorization to access BigQuery.")
            print("Please visit the URL(s) below to grant access:\n")

            for i, auth_info in enumerate(auth_urls, 1):
                print(f"\n--- Authorization {i} ---")
                print(f"Resource: {auth_info['authorization']}")
                print(f"Display Name: {auth_info['display_name']}")
                print(f"\nAuthorization URL:")
                print(auth_info['uri'])
                print("\nSteps to authorize:")
                print("  1. Copy the URL above")
                print("  2. Paste it into your browser")
                print("  3. Sign in with your Google account")
                print("  4. Grant the requested permissions (BigQuery access)")
                print("  5. You'll be redirected to a confirmation page")
                print("  6. Re-run your evaluation tests after authorization")

                # Save to file for easy access
                auth_file = f"results/authorization_{i}.txt"
                os.makedirs("results", exist_ok=True)
                with open(auth_file, 'w') as f:
                    f.write(f"Authorization URL:\n{auth_info['uri']}\n")
                print(f"\n  ✓ URL saved to: {auth_file}")

            print("\n" + "="*70)
            print("IMPORTANT NOTES")
            print("="*70)
            print("• Authorization is required once per agent")
            print("• After authorizing, test queries will return actual BigQuery results")
            print("• Without authorization, agents cannot execute SQL queries")
            print("• This is a v1alpha API limitation for automated testing")
            print("="*70 + "\n")

        else:
            # Check if we got actual results
            has_content = False
            for chunk in response:
                if 'answer' in chunk:
                    for reply in chunk['answer'].get('replies', []):
                        content = reply.get('groundedContent', {}).get('content', {})
                        if content.get('text'):
                            has_content = True
                            break

            if has_content:
                print("\n" + "="*70)
                print("✓ AGENT IS AUTHORIZED")
                print("="*70)
                print("\nYour agent is already authorized and returned a response!")
                print("You can now run evaluation tests without authorization issues.\n")

                # Show sample of the response
                print("Sample response:")
                for chunk in response:
                    if 'answer' in chunk:
                        for reply in chunk['answer'].get('replies', []):
                            content = reply.get('groundedContent', {}).get('content', {})
                            text = content.get('text', '')
                            if text:
                                print(f"  {text[:200]}{'...' if len(text) > 200 else ''}")
                                break
                print()
            else:
                print("\n" + "="*70)
                print("⚠️  UNKNOWN STATE")
                print("="*70)
                print("\nNo authorization required, but no content returned either.")
                print("The agent may be in an unexpected state.\n")
                print("Raw response structure:")
                print(json.dumps(response, indent=2)[:500])
                print("\n...")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
