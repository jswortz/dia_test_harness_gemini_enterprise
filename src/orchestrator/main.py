import click
import json
import logging
import os
import sys
from .agent_client import MockAgentClient, RealAgentClient
from .engine import TestEngine
from dotenv import load_dotenv

load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@click.group()
def cli():
    """DIA Test Harness Orchestrator CLI."""
    pass

@cli.command()
@click.option('--config-file', type=click.Path(exists=True), required=True, help='Path to agent configurations JSON')
@click.option('--golden-set', type=click.Path(exists=True), required=True, help='Path to golden set JSON')
@click.option('--output-file', default='results.json', help='Output file for results')
@click.option('--parallel', default=1, help='Number of parallel agents')
@click.option('--use-real-api', is_flag=True, help='Use real DIA API instead of mock')
def run_all(config_file, golden_set, output_file, parallel, use_real_api):
    """Run the full test suite."""
    logger.info("Starting DIA Test Harness...")
    
    # Load inputs
    with open(config_file, 'r') as f:
        configs = json.load(f)
        
    # Inject Env Vars into Configs if missing
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    dataset_id = os.getenv("BQ_DATASET_ID", "dia_test_dataset")
    
    if use_real_api and not project_id:
         raise click.ClickException("GOOGLE_CLOUD_PROJECT must be set for real API usage.")

    for c in configs:
        if "bq_project_id" not in c and project_id:
            c["bq_project_id"] = project_id
        if "bq_dataset_id" not in c:
            c["bq_dataset_id"] = dataset_id
        
    with open(golden_set, 'r') as f:
        gold_data = json.load(f)
        
    # Init Engine
    # Init Engine
    if use_real_api:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("DIA_LOCATION", "global")
        if not project_id:
             raise click.ClickException("GOOGLE_CLOUD_PROJECT environment variable must be set when using --use-real-api")
        
        engine_id = os.getenv("DIA_ENGINE_ID", "dia-test-engine")
        logger.info(f"Using RealAgentClient with Project: {project_id}, Location: {location}, Engine: {engine_id}")
        client = RealAgentClient(project_id, location, engine_id)
    else:
        logger.info("Using MockAgentClient")
        client = MockAgentClient()
        
    engine = TestEngine(client)
    
    # Run
    start_time = os.times().elapsed
    results = engine.run_suite(configs, gold_data, parallel_agents=parallel)
    total_time = os.times().elapsed - start_time
    
    # Save Results
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
        
    logger.info(f"Test Suite Completed in {total_time:.2f}s. Results saved to {output_file}")
    
    # Simple Report
    correct_count = sum(1 for r in results if r['is_correct'])
    total = len(results)
    if total > 0:
        logger.info(f"Summary: {correct_count}/{total} passed ({(correct_count/total)*100:.1f}%)")
    else:
        logger.info("Summary: No results (0 passed).")

if __name__ == '__main__':
    cli()
