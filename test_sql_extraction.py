#!/usr/bin/env python3
"""
Test script to verify SQL extraction from agent responses.

This script:
1. Loads the golden dataset
2. Queries the deployed agent with each question
3. Parses responses to extract SQL
4. Compares extracted SQL with expected SQL
5. Reports matches/mismatches
"""

import json
import os
import sys
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from evaluation.agent_client import AgentClient
from evaluation.runner import TestRunner
from evaluation.data_loader import GoldenSetLoader


def main():
    # Load environment variables
    load_dotenv()

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")

    if not all([project_id, engine_id, agent_id]):
        print("ERROR: Missing required environment variables:")
        print("  GOOGLE_CLOUD_PROJECT, DIA_ENGINE_ID, DIA_AGENT_ID")
        print("\nPlease set these in your .env file.")
        sys.exit(1)

    print("="*80)
    print("SQL EXTRACTION TEST")
    print("="*80)
    print(f"Project: {project_id}")
    print(f"Location: {location}")
    print(f"Engine: {engine_id}")
    print(f"Agent: {agent_id}")
    print()

    # Initialize components
    print("Initializing agent client...")
    client = AgentClient(project_id, location, engine_id, agent_id)

    # Load golden dataset
    print("Loading golden dataset...")
    loader = GoldenSetLoader()
    golden_set_path = "data/golden_set.json"
    test_cases = loader.load(golden_set_path)

    print(f"Loaded {len(test_cases)} test cases\n")

    # Create a dummy runner just for parsing
    class DummyComparator:
        def compare(self, sql1, sql2):
            return sql1.strip().upper() == sql2.strip().upper()

    runner = TestRunner(
        loader=loader,
        client=client,
        comparator=DummyComparator(),
        judge=None,  # Not needed for this test
        output_path="/tmp/test_extraction.jsonl"
    )

    # Test each question
    results = []
    for i, test_case in enumerate(test_cases, 1):
        question = test_case["nl_question"]
        expected_sql = test_case["expected_sql"]

        print(f"[{i}/{len(test_cases)}] Testing: {question}")

        try:
            # Query 1: Initial question
            raw_response_1 = client.query_agent(question)
            parsed_1 = runner.parse_response(raw_response_1)
            generated_sql = parsed_1["generated_sql"]

            # Extract session ID
            session_id = None
            for chunk in reversed(raw_response_1):
                if "sessionInfo" in chunk and "session" in chunk["sessionInfo"]:
                    session_id = chunk["sessionInfo"]["session"]
                    break

            # Query 2: Follow-up for SQL if not found in first response
            if not generated_sql and session_id:
                raw_response_2 = client.query_agent(
                    "what was the sql query used for the previous answer?",
                    session_id=session_id
                )
                parsed_2 = runner.parse_response(raw_response_2)
                if parsed_2["generated_sql"]:
                    generated_sql = parsed_2["generated_sql"]

            # Compare
            match = generated_sql.strip().upper() == expected_sql.strip().upper()

            result = {
                "question": question,
                "expected_sql": expected_sql,
                "generated_sql": generated_sql,
                "match": match
            }
            results.append(result)

            # Display result
            if match:
                print(f"  ✅ MATCH")
            else:
                print(f"  ❌ MISMATCH")
                print(f"     Expected: {expected_sql}")
                print(f"     Got:      {generated_sql}")

            print()

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append({
                "question": question,
                "expected_sql": expected_sql,
                "error": str(e),
                "match": False
            })
            print()

    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)

    total = len(results)
    matches = sum(1 for r in results if r.get("match", False))
    errors = sum(1 for r in results if "error" in r)

    print(f"Total Tests: {total}")
    print(f"Matches: {matches}")
    print(f"Mismatches: {total - matches - errors}")
    print(f"Errors: {errors}")
    print(f"\nAccuracy: {matches/total*100:.1f}%")

    # Save detailed results
    output_file = "test_sql_extraction_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
