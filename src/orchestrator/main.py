import click
import json
import logging
import os
import sys
from .agent_client import MockAgentClient, RealAgentClient
from .engine import TestEngine
from dotenv import load_dotenv

# Import iterative optimization components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from iterative.optimizer import IterativeOptimizer

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

@cli.command()
@click.option('--config-file', type=click.Path(exists=True), required=True, help='Path to agent configuration JSON')
@click.option('--golden-set', type=click.Path(exists=True), required=True, help='Path to golden set (JSON/CSV/Excel)')
@click.option('--max-iterations', default=10, help='Maximum number of optimization iterations')
def optimize(config_file, golden_set, max_iterations):
    """
    Run iterative optimization for a single agent.

    This command:
    1. Deploys a single agent with the baseline configuration
    2. Runs evaluation against the golden set
    3. Analyzes failures and suggests prompt improvements
    4. Updates the agent via PATCH API
    5. Repeats until user stops or accuracy reaches 100%

    Results are tracked in results/trajectory_history.json
    """
    logger.info("Starting Iterative Agent Optimization...")

    # Load configuration
    with open(config_file, 'r') as f:
        config_data = json.load(f)

    # Handle both single config and multi-variant config files
    if isinstance(config_data, list):
        # Multi-variant config - extract first one or look for "baseline"
        baseline_config = None
        for cfg in config_data:
            if cfg.get("name") == "baseline":
                baseline_config = cfg
                break
        if not baseline_config:
            baseline_config = config_data[0]  # Use first config if no baseline found
        config = baseline_config
    elif isinstance(config_data, dict):
        # Check if it's a wrapped config
        if "configs" in config_data:
            configs_list = config_data["configs"]
            config = configs_list[0] if configs_list else {}
        else:
            # Single config
            config = config_data
    else:
        raise click.ClickException("Invalid config file format")

    # Validate required environment variables
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DIA_LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID")
    dataset_id = os.getenv("BQ_DATASET_ID")

    if not all([project_id, location, engine_id, dataset_id]):
        missing = []
        if not project_id:
            missing.append("GOOGLE_CLOUD_PROJECT")
        if not engine_id:
            missing.append("DIA_ENGINE_ID")
        if not dataset_id:
            missing.append("BQ_DATASET_ID")
        raise click.ClickException(f"Missing required environment variables: {', '.join(missing)}")

    logger.info(f"Configuration:")
    logger.info(f"  Project: {project_id}")
    logger.info(f"  Location: {location}")
    logger.info(f"  Engine: {engine_id}")
    logger.info(f"  Dataset: {dataset_id}")
    logger.info(f"  Config: {config.get('name', 'unknown')}")
    logger.info(f"  Golden Set: {golden_set}")
    logger.info(f"  Max Iterations: {max_iterations}")

    # Initialize and run optimizer
    optimizer = IterativeOptimizer(
        config=config,
        golden_set_path=golden_set,
        project_id=project_id,
        location=location,
        engine_id=engine_id,
        dataset_id=dataset_id,
        max_iterations=max_iterations
    )

    optimizer.run()

    logger.info("Optimization complete!")

if __name__ == '__main__':
    cli()
