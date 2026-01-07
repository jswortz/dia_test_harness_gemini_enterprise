#!/usr/bin/env python3
"""
Test script to verify the evaluation pipeline with a single test case.
Tests the agent_client, evaluator, and runner components.
"""

import os
import sys
import json
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.evaluation.data_loader import GoldenSetLoader
from src.evaluation.agent_client import AgentClient
from src.evaluation.evaluator import SQLComparator, JudgementModel
from src.evaluation.runner import TestRunner

def test_agent_client():
    """Test the agent client directly."""
    load_dotenv()

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")

    print(f"\n{'='*60}")
    print("TESTING AGENT CLIENT")
    print(f"{'='*60}")
    print(f"Project: {project_id}")
    print(f"Location: {location}")
    print(f"Engine: {engine_id}")
    print(f"Agent: {agent_id}")
    print()

    # Initialize client
    client = AgentClient(project_id, location, engine_id, agent_id)

    # Test query
    question = "How many customers are there?"
    print(f"Question: {question}\n")

    response = client.query_agent(question)

    print(f"Response type: {type(response)}")
    print(f"Response is list: {isinstance(response, list)}")
    print(f"Response length: {len(response) if isinstance(response, list) else 'N/A'}")
    print(f"\nRaw response structure:")
    print(json.dumps(response, indent=2)[:1000])
    print("...\n")

    # Parse the response
    thoughts = []
    answers = []
    session_id = None

    for chunk in response:
        if 'answer' in chunk:
            for reply in chunk['answer'].get('replies', []):
                content = reply.get('groundedContent', {}).get('content', {})
                text = content.get('text', '')
                is_thought = content.get('thought', False)

                if is_thought:
                    thoughts.append(text)
                else:
                    answers.append(text)

        if 'sessionInfo' in chunk:
            session_id = chunk['sessionInfo'].get('session')

    print(f"Extracted thoughts: {len(thoughts)} chunks")
    if thoughts:
        print(f"Thought sample: {thoughts[0][:100]}...")

    print(f"\nExtracted answers: {len(answers)} chunks")
    if answers:
        print(f"Answer: {''.join(answers)[:200]}...")

    print(f"\nSession ID: {session_id}")

    # Test follow-up if we have a session
    if session_id:
        print(f"\n{'='*60}")
        print("TESTING SESSION FOLLOW-UP")
        print(f"{'='*60}\n")

        followup_question = "What was the SQL query used for the previous answer?"
        print(f"Follow-up: {followup_question}\n")

        followup_response = client.query_agent(followup_question, session_id=session_id)

        # Parse follow-up
        followup_texts = []
        for chunk in followup_response:
            if 'answer' in chunk:
                for reply in chunk['answer'].get('replies', []):
                    content = reply.get('groundedContent', {}).get('content', {})
                    text = content.get('text', '')
                    if text and not content.get('thought', False):
                        followup_texts.append(text)

        if followup_texts:
            print(f"SQL from follow-up:\n{''.join(followup_texts)}\n")

    return True

def test_full_evaluation():
    """Test the full evaluation pipeline with debug_set.json."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")

    print(f"\n{'='*60}")
    print("TESTING FULL EVALUATION PIPELINE")
    print(f"{'='*60}\n")

    # Initialize components
    loader = GoldenSetLoader()
    client = AgentClient(project_id, location, engine_id, agent_id)
    comparator = SQLComparator()
    judge = JudgementModel(project_id, location)

    output_path = "results/test_evaluation_results.jsonl"
    os.makedirs("results", exist_ok=True)

    runner = TestRunner(loader, client, comparator, judge, output_path)

    # Use debug_set.json for a single test case
    input_path = "data/debug_set.json"

    print(f"Running test with: {input_path}\n")
    runner.run(input_path)

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}\n")

    # Read and display results
    if os.path.exists(output_path):
        with open(output_path, 'r') as f:
            for line in f:
                result = json.loads(line)
                print(f"Question ID: {result.get('question_id')}")
                print(f"Question: {result.get('question')}")
                print(f"Expected SQL: {result.get('expected_sql')}")
                print(f"Generated SQL: {result.get('generated_sql')}")
                print(f"Match: {result.get('is_match')}")
                print(f"Latency: {result.get('latency', 0):.2f}s")

                if result.get('explanation'):
                    print(f"\nLLM Judge Explanation:")
                    print(result.get('explanation'))

                if result.get('error'):
                    print(f"\nERROR: {result.get('error')}")
    else:
        print(f"No results file found at {output_path}")

    print(f"\n{'='*60}\n")

def main():
    """Run all tests."""
    try:
        # Test 1: Direct agent client
        print("\n" + "="*60)
        print("TEST 1: Agent Client Direct Test")
        print("="*60)
        test_agent_client()

        # Test 2: Full evaluation pipeline
        print("\n" + "="*60)
        print("TEST 2: Full Evaluation Pipeline")
        print("="*60)
        test_full_evaluation()

        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n{'='*60}")
        print(f"TEST FAILED: {e}")
        print(f"{'='*60}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
