import click
import json
import logging
import os
import sys
import shutil
from pathlib import Path
from .agent_client import MockAgentClient, RealAgentClient
from .engine import TestEngine
from dotenv import load_dotenv

# Import iterative optimization components
from iterative.optimizer import IterativeOptimizer

load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def clear_results_directory():
    """
    Clear all prior results from the results/ directory.

    Removes:
    - trajectory_history_*.json files
    - eval_train_*.jsonl files
    - OPTIMIZATION_REPORT_*.md files
    - charts/ directory
    - configs/ directory
    - run_* directories

    Preserves:
    - .gitkeep files
    - README files
    """
    results_dir = Path("results")

    if not results_dir.exists():
        logger.info("Results directory does not exist. Nothing to clear.")
        return

    logger.info(f"\n{'='*80}")
    logger.info("CLEARING PRIOR RESULTS")
    logger.info(f"{'='*80}\n")

    deleted_files = []
    deleted_dirs = []
    preserved_files = []

    # Patterns to delete
    delete_patterns = [
        "trajectory_history_*.json",
        "eval_train_*.jsonl*",
        "eval_test_*.jsonl*",
        "OPTIMIZATION_REPORT_*.md",
        "config_iteration_*.json"
    ]

    # Directories to delete
    delete_dirs = ["charts", "configs"]

    # Delete matching files
    for pattern in delete_patterns:
        for file_path in results_dir.glob(pattern):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    deleted_files.append(file_path.name)
                    logger.info(f"  ✓ Deleted: {file_path.name}")
                except Exception as e:
                    logger.warning(f"  ✗ Failed to delete {file_path.name}: {e}")

    # Delete run_* directories
    for run_dir in results_dir.glob("run_*"):
        if run_dir.is_dir():
            try:
                shutil.rmtree(run_dir)
                deleted_dirs.append(run_dir.name)
                logger.info(f"  ✓ Deleted directory: {run_dir.name}/")
            except Exception as e:
                logger.warning(f"  ✗ Failed to delete {run_dir.name}/: {e}")

    # Delete specific subdirectories
    for dir_name in delete_dirs:
        dir_path = results_dir / dir_name
        if dir_path.exists() and dir_path.is_dir():
            try:
                shutil.rmtree(dir_path)
                deleted_dirs.append(dir_name)
                logger.info(f"  ✓ Deleted directory: {dir_name}/")
            except Exception as e:
                logger.warning(f"  ✗ Failed to delete {dir_name}/: {e}")

    # Count preserved files
    for item in results_dir.iterdir():
        if item.is_file() and item.name not in deleted_files:
            preserved_files.append(item.name)

    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("CLEANUP SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Deleted {len(deleted_files)} files")
    logger.info(f"Deleted {len(deleted_dirs)} directories")
    if preserved_files:
        logger.info(f"Preserved {len(preserved_files)} files: {', '.join(preserved_files)}")
    logger.info(f"{'='*80}\n")

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
def deploy(config_file):
    """
    Deploy a new Data Insights Agent (first-time setup).

    This command:
    1. Deploys a single agent with the configuration
    2. Displays OAuth authorization instructions
    3. Saves agent details for future optimization runs

    After deployment, you must authorize the agent via Gemini Enterprise UI
    before running optimization.
    """
    logger.info("Deploying Data Insights Agent (first-time setup)...")

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

    # Import deployer
    from iterative.deployer import SingleAgentDeployer

    # Initialize deployer
    deployer = SingleAgentDeployer(
        project_id=project_id,
        location=location,
        engine_id=engine_id,
        dataset_id=dataset_id
    )

    # Deploy agent
    try:
        agent_id = deployer.deploy_initial(config)

        # Display OAuth authorization instructions
        print(f"\n{'='*80}")
        print("✓ AGENT DEPLOYED SUCCESSFULLY")
        print(f"{'='*80}\n")

        print(f"Agent Details:")
        print(f"  Agent ID: {agent_id}")
        print(f"  Display Name: {deployer.agent_display_name}")
        print(f"  Project: {project_id}")
        print(f"  Location: {location}")
        print(f"  Engine: {engine_id}\n")

        print(f"{'='*80}")
        print("🔧 REQUIRED: Update .env File for Consistent Testing")
        print(f"{'='*80}\n")

        print("To ensure all tests use this agent consistently, update your .env file:\n")
        print(f"  DIA_AGENT_ID={agent_id}\n")

        print("You can do this by running:")
        print(f"  echo 'DIA_AGENT_ID={agent_id}' >> .env\n")
        print("Or manually edit the .env file and update/add the DIA_AGENT_ID line.\n")

        print(f"{'='*80}")
        print("⚠️  IMPORTANT: OAuth Authorization Required (ONE-TIME SETUP)")
        print(f"{'='*80}\n")

        print("Before running optimization, you must authorize the agent to access BigQuery.\n")

        print("OPTION 1: Authorize via Gemini Enterprise UI (Recommended)")
        print(f"{'─'*80}")
        print("1. Navigate to Gemini Enterprise in Google Cloud Console:")
        print(f"   https://console.cloud.google.com/gen-app-builder/engines/{engine_id}/assistants/default_assistant/agents?project={project_id}\n")
        print("2. Find your deployed agent in the agents list")
        print(f"   (Look for: {deployer.agent_display_name})\n")
        print("3. Click on the agent to open its details\n")
        print("4. Click 'Test' or 'Chat' to open the test interface\n")
        print("5. Send a test query (e.g., 'How many customers are there?')\n")
        print("6. The agent will prompt for OAuth authorization")
        print("   - Click the authorization link in the response")
        print("   - Sign in with your Google account")
        print("   - Grant BigQuery access permissions\n")
        print("7. Send the query again to verify it works\n")

        print("OPTION 2: Authorize via CLI Script")
        print(f"{'─'*80}")
        print("1. Run the authorization script (agent ID already configured):")
        print(f"   python scripts/authorize_agent.py\n")
        print("2. Follow the script's instructions to authorize\n")

        print(f"{'='*80}")
        print("NEXT STEPS")
        print(f"{'='*80}\n")

        print("1. Update your .env file with the agent ID (see above)\n")
        print("2. Authorize the agent (one-time, see options above)\n")
        print("3. Run optimization:")
        print(f"   dia-harness optimize \\")
        print(f"     --config-file {config_file} \\")
        print(f"     --golden-set data/golden_set.json\n")

        print(f"{'='*80}")
        print("NOTES:")
        print(f"  • Authorization is one-time per agent and persists across runs")
        print(f"  • All future tests will use the agent ID from .env")
        print(f"  • This ensures consistent testing on the same agent")
        print(f"{'='*80}\n")

        logger.info("Deployment complete!")

    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        raise click.ClickException(str(e))

@cli.command()
@click.option('--config-file', type=click.Path(exists=True), default=None, help='Path to agent configuration JSON (optional - will fetch from deployed agent if not provided)')
@click.option('--golden-set', type=click.Path(exists=True), required=True, help='Path to training set (golden set)')
@click.option('--test-set', type=click.Path(exists=True), default=None, help='Optional path to held-out test set')
@click.option('--max-iterations', default=10, help='Maximum number of optimization iterations')
@click.option('--num-repeats', default=3, help='Number of times to repeat each test (default: 3)')
@click.option('--max-workers', default=10, help='Maximum number of parallel workers for test execution (default: 10)')
@click.option('--auto-accept', is_flag=True, help='Automatically approve all AI-suggested improvements')
@click.option('--clear-prior-results', is_flag=True, help='Clear all prior results before starting optimization')
@click.option('--agent-id', default=None, help='Agent ID to optimize (overrides DIA_AGENT_ID env var)')
def optimize(config_file, golden_set, test_set, max_iterations, num_repeats, max_workers, auto_accept, clear_prior_results, agent_id):
    """
    Run iterative optimization for a single agent.

    PREREQUISITE: Run 'dia-harness deploy' FIRST to deploy and authorize the agent.

    This command:
    1. Finds the existing deployed agent by name (or ID)
    2. Runs evaluation against the golden set (with repeats)
    3. Analyzes failures and suggests prompt improvements
    4. Updates the agent via PATCH API
    5. Repeats until user stops or accuracy reaches 100%

    ARGS:
    - --config-file: Path to agent configuration JSON (optional if agent-id provided)
    - --golden-set: Path to training set (golden set) [REQUIRED]
    - --agent-id: Agent ID to optimize (overrides DIA_AGENT_ID env var)
    - --test-set: Optional path to held-out test set
    - --max-iterations: Maximum number of optimization iterations (default: 10)
    - --num-repeats: Number of times to repeat each test (default: 3)
    - --max-workers: Maximum number of parallel workers (default: 10)
    - --auto-accept: Automatically approve all AI-suggested improvements
    - --clear-prior-results: Clear all prior results before starting

    WORKFLOW:
    1. First time: dia-harness deploy --config-file configs/baseline_config.json
    2. Authorize agent via Gemini Enterprise UI (one-time)
    3. Always:     dia-harness optimize --config-file configs/baseline_config.json --golden-set data/golden_set.json
       OR:         dia-harness optimize --agent-id <ID> --golden-set data/golden_set.json
    """
    # Clear prior results if flag is set
    if clear_prior_results:
        clear_results_directory()

    if auto_accept:
        logger.info("AUTO-ACCEPT MODE ENABLED: Fully automated optimization")

    logger.info("Starting Iterative Agent Optimization...")

    # Validate required environment variables first (needed for both config loading paths)
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

    # Load configuration - either from file or from deployed agent
    if config_file:
        # Load from file (original behavior)
        logger.info(f"Loading configuration from file: {config_file}")
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
    else:
        # Fetch from deployed agent
        logger.info("No config file provided - fetching configuration from deployed agent...")

        # Import deployer
        from iterative.deployer import SingleAgentDeployer

        # Initialize deployer
        deployer = SingleAgentDeployer(
            project_id=project_id,
            location=location,
            engine_id=engine_id,
            dataset_id=dataset_id
        )

        # Find existing agent (prioritize DIA_AGENT_ID env var)
        env_agent_id = os.getenv("DIA_AGENT_ID")
        if env_agent_id:
            logger.info(f"Using agent ID from .env: {env_agent_id}")
            deployer.agent_id = env_agent_id
            deployer.agent_name = f"projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant/agents/{env_agent_id}"
        else:
            raise click.ClickException(
                "DIA_AGENT_ID environment variable must be set when not providing --config-file. "
                "Run 'dia-harness deploy' first to deploy an agent."
            )

        # Fetch config from deployed agent
        config = deployer.get_agent_config()
        if not config:
            raise click.ClickException(
                f"Failed to fetch configuration from deployed agent {env_agent_id}. "
                "Verify the agent exists and is accessible."
            )

        logger.info(f"✓ Successfully fetched configuration from deployed agent")
        logger.info(f"  Config name: {config.get('name', 'unknown')}")

    logger.info(f"Configuration:")
    logger.info(f"  Project: {project_id}")
    logger.info(f"  Location: {location}")
    logger.info(f"  Engine: {engine_id}")
    logger.info(f"  Dataset: {dataset_id}")
    logger.info(f"  Config: {config.get('name', 'unknown')}")
    logger.info(f"  Training Set: {golden_set}")
    if test_set:
        logger.info(f"  Test Set: {test_set}")
    logger.info(f"  Max Iterations: {max_iterations}")
    logger.info(f"  Repeat Measurements: {num_repeats}")
    logger.info(f"  Max Workers: {max_workers}")
    logger.info(f"  Auto-Accept: {auto_accept}")

    # Initialize and run optimizer (always uses existing agent)
    optimizer = IterativeOptimizer(
        config=config,
        golden_set_path=golden_set,
        test_set_path=test_set,
        project_id=project_id,
        location=location,
        engine_id=engine_id,
        dataset_id=dataset_id,
        max_iterations=max_iterations,
        num_repeats=num_repeats,
        max_workers=max_workers,
        auto_accept=auto_accept,
        agent_id=agent_id
    )

    optimizer.run()

    logger.info("Optimization complete!")

if __name__ == '__main__':
    cli()
