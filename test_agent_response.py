#!/usr/bin/env python3
"""
Diagnostic script to check agent response and SQL generation.
"""
import sys
import os
import json
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, 'src')

from evaluation.agent_client import AgentClient
from evaluation.runner import TestRunner
from evaluation.data_loader import GoldenSetLoader
from evaluation.evaluator import SQLComparator, JudgementModel

# Load environment
load_dotenv()

# Get configuration
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
location = os.getenv("DIA_LOCATION", "global")
engine_id = os.getenv("DIA_ENGINE_ID")
agent_id = os.getenv("DIA_AGENT_ID")

print("="*80)
print("AGENT CONFIGURATION CHECK")
print("="*80)
print(f"Project ID: {project_id}")
print(f"Location: {location}")
print(f"Engine ID: {engine_id}")
print(f"Agent ID from .env: {agent_id}")
print()

if not all([project_id, location, engine_id, agent_id]):
    print("❌ ERROR: Missing environment variables!")
    print("Required: GOOGLE_CLOUD_PROJECT, DIA_LOCATION, DIA_ENGINE_ID, DIA_AGENT_ID")
    sys.exit(1)

# Initialize client
print("Initializing agent client...")
client = AgentClient(project_id, location, engine_id, agent_id)

# Test query
test_question = "Show me sales for the month of Oct 2025 for US market"
print(f"\nTesting with question: {test_question}")
print("="*80)

# Create session
session_id = client.create_session()
print(f"✓ Session created: {session_id}\n")

# Query 1: Initial question
print("QUERY 1: Sending initial question...")
raw_response_1 = client.query_agent(test_question, session_id=session_id)

print(f"\nRaw Response Structure:")
print(f"  Type: {type(raw_response_1)}")
print(f"  Length: {len(raw_response_1) if isinstance(raw_response_1, list) else 'N/A'}")
print(f"\nFull Raw Response (formatted):")
print(json.dumps(raw_response_1, indent=2)[:2000] + "..." if len(json.dumps(raw_response_1, indent=2)) > 2000 else json.dumps(raw_response_1, indent=2))

# Parse with runner
loader = GoldenSetLoader()
comparator = SQLComparator()
judge = JudgementModel(project_id, location)
runner = TestRunner(loader, client, comparator, judge, "test_output.jsonl")

parsed_1 = runner.parse_response(raw_response_1)
print("\n" + "="*80)
print("PARSED RESPONSE 1:")
print("="*80)
print(f"Thoughts: {parsed_1['thoughts'][:200] if parsed_1['thoughts'] else '(empty)'}...")
print(f"Response: {parsed_1['response'][:200] if parsed_1['response'] else '(empty)'}...")
print(f"Generated SQL: {parsed_1['generated_sql'][:200] if parsed_1['generated_sql'] else '(empty)'}...")

# Query 2: Follow-up for SQL
print("\n" + "="*80)
print("QUERY 2: Asking for SQL...")
raw_response_2 = client.query_agent(
    "what was the sql query used for the previous answer?",
    session_id=session_id
)

print(f"\nRaw Response 2 Structure:")
print(f"  Type: {type(raw_response_2)}")
print(f"  Length: {len(raw_response_2) if isinstance(raw_response_2, list) else 'N/A'}")
print(f"\nFull Raw Response 2 (formatted):")
print(json.dumps(raw_response_2, indent=2)[:2000] + "..." if len(json.dumps(raw_response_2, indent=2)) > 2000 else json.dumps(raw_response_2, indent=2))

parsed_2 = runner.parse_response(raw_response_2)
print("\n" + "="*80)
print("PARSED RESPONSE 2:")
print("="*80)
print(f"Thoughts: {parsed_2['thoughts'][:200] if parsed_2['thoughts'] else '(empty)'}...")
print(f"Response: {parsed_2['response'][:200] if parsed_2['response'] else '(empty)'}...")
print(f"Generated SQL: {parsed_2['generated_sql'][:200] if parsed_2['generated_sql'] else '(empty)'}...")

# Final SQL
final_sql = parsed_2['generated_sql'] or parsed_1['generated_sql']
print("\n" + "="*80)
print("FINAL RESULT:")
print("="*80)
if final_sql:
    print(f"✓ SQL Generated ({len(final_sql)} chars)")
    print(f"\n{final_sql}\n")
else:
    print("❌ NO SQL GENERATED!")
    print("\n⚠️  POSSIBLE ISSUES:")
    print("1. Agent is not authorized (requires OAuth)")
    print("2. Agent is not a Data Insights Agent (wrong agent type)")
    print("3. Agent configuration is missing schema/tables")
    print(f"4. Wrong agent ID in .env (current: {agent_id})")
    print("\nTo check:")
    print(f"- Verify agent exists: gcloud alpha discovery-engine list agents --engine={engine_id} --location={location}")
    print(f"- Check agent type: Should be 'DATA_INSIGHTS_AGENT'")
    print(f"- Verify OAuth authorization is complete")

print("\n" + "="*80)
