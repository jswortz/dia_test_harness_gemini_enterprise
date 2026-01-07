
import os
import sys
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.evaluation.data_loader import GoldenSetLoader
from src.evaluation.agent_client import AgentClient
from src.evaluation.evaluator import SQLComparator, JudgementModel
from src.evaluation.runner import TestRunner

def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    location = os.getenv("DIA_LOCATION", "global").lower()
    engine_id = os.getenv("DIA_ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID")
    
    if not all([project_id, engine_id, agent_id]):
        print("Error: Missing required environment variables.")
        print(f"PROJECT_ID: {project_id}")
        print(f"DIA_ENGINE_ID: {engine_id}")
        print(f"DIA_AGENT_ID: {agent_id}")
        return

    print(f"Running Golden Test with:")
    print(f"  Project: {project_id}")
    print(f"  Location: {location}")
    print(f"  Engine: {engine_id}")
    print(f"  Agent: {agent_id}")

    loader = GoldenSetLoader()
    client = AgentClient(project_id, location, engine_id, agent_id)
    comparator = SQLComparator()
    judge = JudgementModel(project_id, location)
    
    output_path = "results/golden_test_results.jsonl"
    os.makedirs("results", exist_ok=True)
    
    runner = TestRunner(loader, client, comparator, judge, output_path)
    
    input_path = "data/golden_set.json"
    runner.run(input_path)

if __name__ == "__main__":
    main()
