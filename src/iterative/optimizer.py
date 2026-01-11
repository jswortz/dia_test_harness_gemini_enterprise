"""
IterativeOptimizer: Main orchestrator for closed-loop agent optimization.

Coordinates:
- Agent deployment (initial + PATCH updates)
- Evaluation against golden set
- Trajectory tracking
- Prompt improvement suggestions
- User interaction for iteration control
"""

from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from .deployer import SingleAgentDeployer
from .evaluator import SingleAgentEvaluator, get_vertex_ai_location
from .tracker import TrajectoryTracker
from .prompt_improver import PromptImprover
from .config_analyzer import ConfigFieldAnalyzer
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from evaluation.agent_client import AgentAuthorizationError


def validate_prompt_improvement(
    old_prompt: str,
    new_prompt: str,
    verbose: bool = True
) -> Tuple[bool, str]:
    """
    Validates that prompt changes are sensible improvements.

    Checks:
    1. Size reduction limit (>30% reduction is suspicious)
    2. Instruction vs. Code ratio (should be instructions, not SQL)
    3. Key sections preserved (tables, joins, formulas, etc.)
    4. Minimum prompt length (should be substantial)

    Args:
        old_prompt: Original prompt text
        new_prompt: Suggested new prompt text
        verbose: If True, log validation details

    Returns:
        Tuple[bool, str]: (is_valid, reason)
    """
    # Check 1: Size reduction limit (>30% reduction is suspicious)
    size_change_pct = (len(new_prompt) - len(old_prompt)) / len(old_prompt) * 100

    if size_change_pct < -30.0:
        reason = f"Prompt size reduced by {abs(size_change_pct):.1f}% - likely corruption"
        if verbose:
            logging.warning(f"❌ Validation failed: {reason}")
        return False, reason

    # Check 2: Instruction vs. Code ratio
    instruction_keywords = ['must', 'always', 'never', 'should', 'rule',
                           'formula', 'when', 'if', 'critical', 'important']
    sql_keywords = ['select', 'from', 'where', 'join', 'group by',
                   'order by', 'union', 'with']

    instruction_count = sum(new_prompt.lower().count(word) for word in instruction_keywords)
    sql_count = sum(new_prompt.lower().count(word) for word in sql_keywords)

    # If SQL keywords dominate (2x more than instructions), likely code not instructions
    if sql_count > instruction_count * 2 and sql_count > 10:
        reason = f"Prompt has {sql_count} SQL keywords vs {instruction_count} instruction keywords - appears to be code, not instructions"
        if verbose:
            logging.warning(f"❌ Validation failed: {reason}")
        return False, reason

    # Check 3: Key sections preserved
    required_keywords = ['table', 'join', 'formula', 'metric', 'aggregat']
    missing_sections = []

    for keyword in required_keywords:
        if keyword in old_prompt.lower() and keyword not in new_prompt.lower():
            missing_sections.append(keyword)

    if missing_sections:
        reason = f"Critical sections removed: {', '.join(missing_sections)}"
        if verbose:
            logging.warning(f"❌ Validation failed: {reason}")
        return False, reason

    # Check 4: Minimum prompt length (should be substantial)
    if len(new_prompt) < 500:
        reason = f"Prompt too short ({len(new_prompt)} chars) - needs comprehensive instructions"
        if verbose:
            logging.warning(f"❌ Validation failed: {reason}")
        return False, reason

    # All checks passed
    if verbose:
        logging.info(f"✅ Prompt validation passed:")
        logging.info(f"   Size change: {size_change_pct:+.1f}%")
        logging.info(f"   Instruction keywords: {instruction_count}")
        logging.info(f"   SQL keywords: {sql_count}")

    return True, "Validation passed"




class IterativeOptimizer:
    """
    Orchestrates the iterative optimization loop for a single Data Insights Agent.

    Flow:
    1. Deploy agent (or use existing)
    2. Run evaluation
    3. Calculate metrics
    4. Track in trajectory
    5. Display results with comparison to previous iteration
    6. If failures exist:
       - Analyze failures with LLM
       - Suggest prompt improvements
       - Get user approval/edits
       - PATCH agent with new prompt
    7. Ask user to continue
    8. Repeat until user stops or accuracy reaches 100%
    """

    def __init__(
        self,
        config: Dict[str, Any],
        golden_set_path: str,
        project_id: str,
        location: str,
        engine_id: str,
        dataset_id: str,
        max_iterations: int = 10,
        num_repeats: int = 3,
        max_workers: int = 10,
        test_set_path: Optional[str] = None,
        auto_accept: bool = False
    ):
        """
        Initialize optimizer.

        PREREQUISITE: Agent must already be deployed via 'dia-harness deploy' command.

        Args:
            config: Agent configuration (name, nl2sql_prompt, params, description)
            golden_set_path: Path to golden set file (JSON/CSV/Excel) - training set
            project_id: Google Cloud project ID
            location: Location (e.g., "global")
            engine_id: Discovery Engine ID
            dataset_id: BigQuery dataset ID
            max_iterations: Maximum number of iterations (safety limit)
            num_repeats: Number of times to repeat each test (default: 3)
            max_workers: Maximum number of parallel workers for test execution (default: 10)
            test_set_path: Optional path to held-out test set (not used for optimization)
            auto_accept: If True, automatically approve all improvements without user input
        """
        self.config = config
        self.golden_set_path = golden_set_path
        self.test_set_path = test_set_path
        self.project_id = project_id
        self.location = location
        self.engine_id = engine_id
        self.dataset_id = dataset_id
        self.max_iterations = max_iterations
        self.num_repeats = num_repeats
        self.max_workers = max_workers
        self.auto_accept = auto_accept

        # Initialize components (will be created after deployment)
        self.deployer: Optional[SingleAgentDeployer] = None
        self.evaluator: Optional[SingleAgentEvaluator] = None
        self.test_evaluator: Optional[SingleAgentEvaluator] = None
        self.tracker: Optional[TrajectoryTracker] = None
        self.improver: Optional[PromptImprover] = None
        self.config_analyzer: Optional[ConfigFieldAnalyzer] = None

        self.agent_id: Optional[str] = None
        self.current_prompt: str = ""
        self.current_params: Dict[str, Any] = {}
        self.current_config: Dict[str, Any] = config.copy()
        self.config_changes_description: str = ""  # Track all config changes

        # Best config tracking for rollback
        self.best_config: Optional[Dict[str, Any]] = None
        self.best_accuracy: float = 0.0
        self.best_iteration: int = 0

    def run(self):
        """
        Run the iterative optimization loop.

        Main loop:
        - Deploy/patch agent
        - Evaluate
        - Track results
        - Suggest improvements
        - Ask to continue
        """
        # Generate timestamp for this optimization run
        from datetime import datetime
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create run-specific results folder for isolation
        self.run_dir = Path(f"results/run_{self.run_timestamp}")
        self.run_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*80}")
        print("ITERATIVE AGENT OPTIMIZATION")
        print(f"{'='*80}\n")
        print(f"Run ID: {self.run_timestamp}")
        print(f"Run Directory: {self.run_dir}")
        print(f"Config: {self.config.get('name', 'baseline')}")
        print(f"Golden Set: {self.golden_set_path}")
        print(f"Max Iterations: {self.max_iterations}\n")

        # Initialize components
        self._initialize_components()

        iteration = 1

        while iteration <= self.max_iterations:
            print(f"\n{'='*80}")
            print(f"ITERATION {iteration}")
            print(f"{'='*80}\n")

            try:
                # Step 1: Find existing agent (first iteration only)
                if iteration == 1:
                    # Always find existing agent - deployment happens via 'deploy' command
                    self._find_existing_agent()

                # Step 2: Run evaluations in parallel (training + test if provided)
                if self.test_set_path:
                    # Run both evaluations in parallel
                    results, metrics, failures, test_results, test_metrics = self._run_parallel_evaluations()
                else:
                    # Only run training evaluation
                    results, metrics, failures = self._run_evaluation()
                    test_results, test_metrics = None, None

                # Step 3: Initialize tracking variables for this iteration
                suggested_config = None
                config_approved = True
                deployment_success = True
                prompt_changes = self._get_prompt_changes(iteration)
                iteration_tracked = False  # Track if we've already saved this iteration

                # Step 4: Display results with comparison
                self._display_results(iteration, metrics, test_metrics, failures)

                # Step 5: Check if perfect score
                current_accuracy = self._extract_accuracy(metrics)
                if current_accuracy >= 100.0:
                    print(f"\n{'='*80}")
                    print("PERFECT SCORE ACHIEVED!")
                    print(f"{'='*80}\n")
                    print("All tests passed. Optimization complete.")

                    # Track this perfect iteration before exiting
                    self.tracker.add_iteration(
                        iteration_num=iteration,
                        config=self._get_current_config(),
                        results=results,
                        metrics=metrics,
                        failures=failures,
                        prompt_changes=prompt_changes,
                        suggested_config=None,
                        config_approved=True,
                        deployment_success=True,
                        test_results=test_results,
                        test_metrics=test_metrics
                    )
                    self.tracker.save()
                    iteration_tracked = True
                    break

                # Step 6: Analyze failures and suggest improvements to ALL config fields
                # CRITICAL: Only use TRAINING data here to avoid test set leakage
                # Test results (test_results, test_metrics) are NEVER used for optimization
                if failures:
                    # Get improved config from _improve_prompt
                    # IMPORTANT: failures and results are from TRAINING SET ONLY
                    improved_prompt, change_description = self._improve_prompt(failures, results)

                    # VALIDATION: Check that improved_prompt is actually a prompt, not SQL
                    if improved_prompt.strip().upper().startswith(('SELECT', 'WITH', 'INSERT', 'UPDATE')):
                        logging.error(f"🔴 CORRUPTION DETECTED: improved_prompt is SQL code, not a prompt!")
                        logging.error(f"Prompt preview: {improved_prompt[:200]}")
                        print(f"\n🔴 ERROR: Prompt improvement produced SQL code instead of a prompt!")
                        print(f"   This indicates a bug in the prompt improvement logic.")
                        print(f"   Skipping this iteration to prevent corruption.")
                        break

                    # Store suggested config (BEFORE applying changes)
                    suggested_config = self.current_config.copy()
                    suggested_config["nl2sql_prompt"] = improved_prompt

                    # Check if ANY config field changed (not just prompt)
                    config_changed = (
                        improved_prompt != self.current_prompt or
                        self.current_config.get("tool_description") != self.config.get("tool_description") or
                        self.current_config.get("schema_description") != self.config.get("schema_description") or
                        self.current_config.get("nl2sql_examples") != self.config.get("nl2sql_examples") or
                        self.current_config.get("nl2py_prompt") != self.config.get("nl2py_prompt")
                    )

                    if config_changed:
                        # Validate prompt improvement before deployment
                        is_valid, validation_reason = validate_prompt_improvement(
                            self.current_prompt,
                            improved_prompt,
                            verbose=True
                        )

                        if not is_valid:
                            print(f"\n{'='*80}")
                            print(f"❌ PROMPT VALIDATION FAILED")
                            print(f"{'='*80}")
                            print(f"Reason: {validation_reason}")
                            print(f"\nReverting nl2sql_prompt to current version.")
                            print(f"Other field improvements (if any) will still be applied.")
                            print(f"{'='*80}\n")

                            # Keep current prompt, update only other fields
                            improved_prompt = self.current_prompt
                            suggested_config["nl2sql_prompt"] = self.current_prompt

                            # Log rejected prompt for debugging
                            rejected_prompts_dir = self.run_dir / "rejected_prompts"
                            rejected_prompts_dir.mkdir(exist_ok=True)
                            with open(rejected_prompts_dir / f"iteration_{iteration}.txt", 'w') as f:
                                f.write(f"Validation failed: {validation_reason}\n\n")
                                f.write(f"Rejected prompt:\n{suggested_config.get('nl2sql_prompt', '')}\n\n")
                                f.write(f"Current prompt (kept):\n{self.current_prompt}\n")

                        # Save suggested config snapshot
                        self._save_config_snapshot(iteration, suggested_config, config_type="suggested")

                        # Update all current state variables
                        self.current_prompt = improved_prompt
                        self.config_changes_description = change_description

                        # PATCH agent with FULL configuration (all fields)
                        print("\n📤 Deploying configuration changes to agent...")
                        print(f"Changes: {change_description}")

                        success = self.deployer.update_prompt(
                            new_prompt=improved_prompt,
                            params=self.current_params,
                            full_config=self.current_config  # Pass complete config
                        )

                        deployment_success = success

                        if not success:
                            # Deployment failed after retries
                            error_msg = "❌ CRITICAL: Failed to update agent after 3 retry attempts."
                            print(f"\n{'='*80}")
                            print(error_msg)
                            print(f"{'='*80}\n")

                            # Track failure immediately
                            self.tracker.add_iteration(
                                iteration_num=iteration,
                                config=self._get_current_config(),
                                results=results,
                                metrics=metrics,
                                failures=failures,
                                prompt_changes=prompt_changes,
                                suggested_config=suggested_config,
                                config_approved=config_approved,
                                deployment_success=False,
                                test_results=test_results,
                                test_metrics=test_metrics
                            )
                            self.tracker.save()
                            iteration_tracked = True  # Mark as tracked

                            if self.auto_accept:
                                # Fail fast in auto-accept mode
                                print("Auto-accept mode: Cannot continue with deployment failures.")
                                print("Please check agent logs and retry manually.\n")
                                raise RuntimeError("Agent deployment failed in auto-accept mode")
                            else:
                                # Ask user what to do
                                print("Options:")
                                print("  1. Continue with old configuration (not recommended)")
                                print("  2. Stop optimization and investigate")
                                choice = input("\nContinue with old config? (y/n): ").strip().lower()
                                if choice != 'y':
                                    print("Stopping optimization due to deployment failure.")
                                    break
                        else:
                            print("✓ Configuration successfully deployed to agent")

                        # Save final config snapshot
                        self._save_config_snapshot(iteration, self.current_config, config_type="final")
                    else:
                        print("\n✓ No configuration changes. Keeping current settings.")
                        # Still save config snapshot for iteration tracking
                        self._save_config_snapshot(iteration, self.current_config, config_type="final")
                else:
                    # No failures - save current config
                    self._save_config_snapshot(iteration, self.current_config, config_type="final")

                # Step 7: Track iteration with ALL metadata (if not already tracked)
                if not iteration_tracked:
                    self.tracker.add_iteration(
                        iteration_num=iteration,
                        config=self._get_current_config(),
                        results=results,
                        metrics=metrics,
                        failures=failures,
                        prompt_changes=prompt_changes,
                        suggested_config=suggested_config,
                        config_approved=config_approved,  # Always True for now (user accepted or auto-accepted)
                        deployment_success=deployment_success,
                        test_results=test_results,
                        test_metrics=test_metrics
                    )
                    self.tracker.save()

                # Step 7.5: Check for rollback (if accuracy degraded significantly)
                current_accuracy = self._extract_accuracy(metrics)

                # Check if we should rollback (>5pp drop from best)
                if self.best_config and current_accuracy < self.best_accuracy - 5.0:
                    print(f"\n{'='*80}")
                    print(f"⚠️  PERFORMANCE REGRESSION DETECTED")
                    print(f"{'='*80}")
                    print(f"Current accuracy: {current_accuracy:.2f}%")
                    print(f"Best accuracy: {self.best_accuracy:.2f}% (Iteration {self.best_iteration})")
                    print(f"Regression: {self.best_accuracy - current_accuracy:.2f} percentage points")
                    print(f"\n🔄 ROLLING BACK to best configuration...")

                    # Rollback to best config
                    self.deployer.update_prompt(
                        self.best_config['nl2sql_prompt'],
                        full_config=self.best_config
                    )

                    # Update current config to best
                    self.current_config = self.best_config.copy()
                    self.current_prompt = self.best_config['nl2sql_prompt']

                    # Mark this iteration as rollback in tracker
                    if self.tracker.history['iterations']:
                        self.tracker.history['iterations'][-1]['action'] = 'rollback'
                        self.tracker.history['iterations'][-1]['rollback_to_iteration'] = self.best_iteration
                        self.tracker.save()

                    print(f"✅ Rolled back to Iteration {self.best_iteration} configuration")
                    print(f"{'='*80}\n")

                # Update best if current is better
                if current_accuracy > self.best_accuracy:
                    self.best_config = self.current_config.copy()
                    self.best_accuracy = current_accuracy
                    self.best_iteration = iteration
                    print(f"\n🏆 New best accuracy: {self.best_accuracy:.2f}% (Iteration {iteration})\n")

                # Step 7.6: Ask user to continue
                if not self._ask_to_continue(iteration):
                    break

                iteration += 1

            except AgentAuthorizationError as e:
                # Agent requires OAuth authorization - stop optimization immediately
                self._handle_authorization_error(e)
                return  # Exit optimization loop

        # Final summary
        self._display_final_summary()

        # Generate visualization and reports
        self._generate_artifacts()

    def _initialize_components(self):
        """Initialize all components."""
        self.deployer = SingleAgentDeployer(
            project_id=self.project_id,
            location=self.location,
            engine_id=self.engine_id,
            dataset_id=self.dataset_id
        )

        self.tracker = TrajectoryTracker(
            agent_name=self.config.get("name", "baseline"),
            timestamp=self.run_timestamp,
            output_path=str(self.run_dir / f"trajectory_history_{self.run_timestamp}.json")
        )

        # Initialize prompt improver lazily (when first failure occurs)
        # to avoid blocking during initialization
        # self.improver will be created in _improve_prompt() if needed

        # Initialize prompt and params from config
        self.current_prompt = self.config.get("nl2sql_prompt", "")
        self.current_params = self.config.get("params", {})
        self.prompt_change_description = "Initial configuration"

    def _find_existing_agent(self):
        """Find and use existing agent (must be pre-deployed via 'deploy' command)."""
        print(f"\n{'='*80}")
        print("FINDING EXISTING AGENT")
        print(f"{'='*80}\n")

        # First priority: Use DIA_AGENT_ID from environment if set
        env_agent_id = os.getenv("DIA_AGENT_ID")
        if env_agent_id:
            print(f"Found DIA_AGENT_ID in environment: {env_agent_id}")
            print(f"Verifying agent exists...")

            # CRITICAL: Verify the agent actually exists before using it
            if self.deployer.verify_agent_exists(env_agent_id):
                self.agent_id = env_agent_id
                print(f"✓ Agent verified and ready: {self.agent_id}")
                print(f"  Display Name: {self.deployer.agent_display_name}\n")
            else:
                print(f"❌ ERROR: Agent ID {env_agent_id} from .env does not exist!")
                print(f"  The agent may have been deleted or the ID is incorrect.\n")
                print(f"  Falling back to search by display name...\n")
                env_agent_id = None  # Clear and fall back to display name search

        # Fallback: Search by display name (if DIA_AGENT_ID not set or verification failed)
        if not env_agent_id:
            config_name = self.config.get("name", "baseline")
            display_name = self.config.get("display_name", f"Data Agent - {config_name}")

            print(f"Searching for existing agent: {display_name}")
            self.agent_id = self.deployer.find_existing_agent(display_name)

            if not self.agent_id:
                # Agent not found - cannot proceed
                print(f"\n{'='*80}")
                print("❌ ERROR: Agent Not Found")
                print(f"{'='*80}\n")
                print(f"No agent found with display name: {display_name}\n")
                print(f"REQUIRED SETUP:")
                print(f"1. Deploy the agent first:")
                print(f"   dia-harness deploy --config-file {self.config.get('name', 'baseline')}_config.json\n")
                print(f"2. Authorize via Gemini Enterprise UI (one-time)\n")
                print(f"3. Then run this optimize command again\n")
                print(f"{'='*80}\n")
                raise ValueError(f"Agent not found: {display_name}. Run 'dia-harness deploy' first.")

        print(f"\n✓ Using existing agent: {self.agent_id}\n")

        # IMPORTANT: Apply initial config if provided via --config-file
        # This ensures iteration 1 starts with the user-provided config, not the old deployed config
        print(f"Applying initial configuration to agent...")

        # Retry logic for initial config application (critical for baseline accuracy)
        max_retries = 3
        success = False
        for attempt in range(1, max_retries + 1):
            print(f"  Attempt {attempt}/{max_retries}...")
            success = self.deployer.update_prompt(
                new_prompt=self.current_prompt,
                params=self.current_params,
                full_config=self.current_config
            )
            if success:
                print(f"✓ Initial config applied successfully\n")
                break
            elif attempt < max_retries:
                import time
                wait_time = 5 * attempt  # Exponential backoff: 5s, 10s, 15s
                print(f"⚠️  Attempt {attempt} failed. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"❌ ERROR: Failed to apply initial config after {max_retries} attempts.")
                print(f"   The optimization will continue, but iteration 1 may use an old config.")
                print(f"   Consider rerunning with a fresh deployment.\n")

        # Create evaluator now that we have agent_id
        self.evaluator = SingleAgentEvaluator(
            agent_id=self.agent_id,
            project_id=self.project_id,
            location=self.location,
            engine_id=self.engine_id,
            output_path=str(self.run_dir / f"eval_train_{self.run_timestamp}.jsonl"),
            timestamp=self.run_timestamp,
            max_workers=self.max_workers,
            schema_description=self.config.get("schema_description", "")
        )

    def _run_evaluation(self) -> tuple:
        """Run evaluation with repeats and return results, metrics, failures.

        Note: Each evaluation already runs repeats in parallel internally.
        """
        if self.num_repeats > 1:
            return self.evaluator.evaluate_with_repeats(
                self.golden_set_path,
                num_repeats=self.num_repeats
            )
        else:
            # Single measurement (backwards compatible)
            return self.evaluator.evaluate(self.golden_set_path)

    def _run_test_evaluation(self) -> tuple:
        """Run evaluation on held-out test set.

        Note: Evaluation already runs repeats in parallel internally.
        """
        print(f"\n{'─'*80}")
        print("EVALUATING ON TEST SET (HELD-OUT)")
        print(f"{'─'*80}\n")

        if not self.test_evaluator:
            self.test_evaluator = SingleAgentEvaluator(
                agent_id=self.agent_id,
                project_id=self.project_id,
                location=self.location,
                engine_id=self.engine_id,
                output_path=str(self.run_dir / f"eval_test_{self.run_timestamp}.jsonl"),
                timestamp=self.run_timestamp,
                max_workers=self.max_workers,
                schema_description=self.config.get("schema_description", "")
            )

        if self.num_repeats > 1:
            results, metrics, failures = self.test_evaluator.evaluate_with_repeats(
                self.test_set_path,
                num_repeats=self.num_repeats
            )
        else:
            results, metrics, failures = self.test_evaluator.evaluate(self.test_set_path)

        return results, metrics, failures

    def _run_parallel_evaluations(self) -> tuple:
        """Run training and test evaluations in parallel.

        Returns:
            Tuple of (train_results, train_metrics, train_failures, test_results, test_metrics)
        """
        print(f"\n{'='*80}")
        print("RUNNING PARALLEL EVALUATIONS (TRAINING + TEST)")
        print(f"{'='*80}\n")

        # Initialize test evaluator if needed
        if not self.test_evaluator:
            self.test_evaluator = SingleAgentEvaluator(
                agent_id=self.agent_id,
                project_id=self.project_id,
                location=self.location,
                engine_id=self.engine_id,
                output_path=str(self.run_dir / f"eval_test_{self.run_timestamp}.jsonl"),
                timestamp=self.run_timestamp,
                max_workers=self.max_workers,
                schema_description=self.config.get("schema_description", "")
            )

        # Execute both evaluations in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both evaluation tasks
            train_future = executor.submit(self._run_evaluation)
            test_future = executor.submit(self._run_test_evaluation)

            # Wait for both to complete and collect results
            train_results, train_metrics, train_failures = train_future.result()
            test_results, test_metrics, test_failures = test_future.result()

        print(f"\n{'='*80}")
        print("PARALLEL EVALUATIONS COMPLETE")
        print(f"{'='*80}\n")

        return train_results, train_metrics, train_failures, test_results, test_metrics

    def _display_results(self, iteration: int, metrics: Dict[str, Any], test_metrics: Optional[Dict[str, Any]], failures: list):
        """Display results with comparison to previous iteration."""
        print(f"\n{'='*80}")
        print(f"ITERATION {iteration} RESULTS")
        print(f"{'='*80}\n")

        # Display training metrics
        print("TRAINING SET:")
        self._display_metrics_block(metrics)

        # Display test metrics if available
        if test_metrics:
            print(f"\n{'─'*80}")
            print("TEST SET (HELD-OUT):")
            self._display_metrics_block(test_metrics)

            # Check for overfitting
            train_acc = self._extract_accuracy(metrics)
            test_acc = self._extract_accuracy(test_metrics)
            gap = train_acc - test_acc
            if gap > 10:
                print(f"\n⚠️  WARNING: Large train/test gap ({gap:.1f}%) suggests overfitting!")

    def _display_metrics_block(self, metrics: Dict[str, Any]):
        """Display a block of metrics (supports both single and repeat measurements)."""
        # Check if this is aggregated metrics (from repeats)
        if isinstance(metrics.get('accuracy'), dict):
            # Repeat measurements
            acc = metrics['accuracy']
            print(f"  Accuracy: {acc['mean']:.2f}% ± {acc['std']:.2f}%")
            print(f"    Range: {acc['min']:.2f}% - {acc['max']:.2f}%")
            print(f"    Individual runs: {acc['values']}")

            exact = metrics['exact_match']
            print(f"  ✓ Exact match: {exact['mean']:.1f} ± {exact['std']:.1f}")

            semantic = metrics['semantically_equivalent']
            print(f"  ✓ Semantically equivalent: {semantic['mean']:.1f} ± {semantic['std']:.1f}")

            fails = metrics['failures']
            print(f"  ✗ Failures: {fails['mean']:.1f} ± {fails['std']:.1f}")
        else:
            # Single measurement
            print(f"  Accuracy: {metrics['accuracy']:.2f}% ({metrics['total'] - metrics['failures']}/{metrics['total']} tests passed)")
            print(f"  ✓ Exact match: {metrics['exact_match']}")
            print(f"  ✓ Semantically equivalent: {metrics['semantically_equivalent']}")
            print(f"  ✗ Failures: {metrics['failures']}")
            if metrics.get('error_count', 0) > 0:
                print(f"  ⚠ Errors: {metrics['error_count']}")

    def _extract_accuracy(self, metrics: Dict[str, Any]) -> float:
        """Extract accuracy value (handles both single and repeat measurements)."""
        if isinstance(metrics.get('accuracy'), dict):
            return metrics['accuracy']['mean']
        return metrics.get('accuracy', 0.0)

        # Compare to previous iteration
        if iteration > 1:
            last_iteration = self.tracker.get_last_iteration()
            if last_iteration and last_iteration['iteration'] == iteration:
                # Get previous iteration (iteration - 1)
                prev_iteration = self.tracker.get_iteration(iteration - 1)
                if prev_iteration:
                    prev_accuracy = prev_iteration['metrics']['accuracy']
                    delta = metrics['accuracy'] - prev_accuracy

                    print(f"\nChange from Iteration {iteration - 1}:")
                    if delta > 0:
                        print(f"  📈 Accuracy: {prev_accuracy}% → {metrics['accuracy']}% (+{delta}%)")
                    elif delta < 0:
                        print(f"  📉 Accuracy: {prev_accuracy}% → {metrics['accuracy']}% ({delta}%)")
                    else:
                        print(f"  ➡️  Accuracy: {prev_accuracy}% → {metrics['accuracy']}% (no change)")

                    # Show which questions changed status
                    comparison = self.tracker.compare_iterations(iteration - 1, iteration)
                    if comparison.get('resolved_issues'):
                        print(f"\n  ✓ Resolved Issues ({len(comparison['resolved_issues'])}):")
                        for issue in comparison['resolved_issues']:
                            print(f"    - {issue['question']}")

                    if comparison.get('new_failures'):
                        print(f"\n  ✗ New Failures ({len(comparison['new_failures'])}):")
                        for failure in comparison['new_failures']:
                            print(f"    - {failure['question']}")

    def _improve_prompt(self, failures: list, results: list) -> tuple:
        """Analyze failures and improve all relevant configuration fields.

        **CRITICAL: This method must ONLY receive TRAINING data to avoid data leakage.**
        Test set data must NEVER be passed to this method, as it would leak
        information from the held-out test set into the optimization process.

        This method:
        1. Uses ConfigFieldAnalyzer to determine which fields need improvement
        2. Uses PromptImprover to generate improved values for those fields
        3. Returns updated config and description of changes

        Args:
            failures: List of failed test cases FROM TRAINING SET ONLY
            results: List of all test results FROM TRAINING SET ONLY (for extracting successes)

        Returns:
            Tuple of (improved_prompt, change_description) for backward compatibility
            Side effect: Updates self.current_config with all field changes
        """
        print(f"\n{'='*80}")
        print("CONFIGURATION ANALYSIS & IMPROVEMENT")
        print(f"{'='*80}\n")

        # Step 1: Extract previous iteration metrics for trajectory analysis
        # This enables regression detection and context-aware improvements
        previous_metrics = None
        if len(self.tracker.history.get("iterations", [])) > 0:
            last_iteration = self.tracker.get_last_iteration()
            if last_iteration:
                eval_data = last_iteration.get("evaluation", {})
                if "train" in eval_data:
                    previous_metrics = eval_data["train"]
                    print(f"📊 Trajectory Context: Using previous iteration metrics for comparison")

        # Step 2: Fetch current config from deployed agent via API
        # This ensures we're analyzing the actual deployed config, not just in-memory state
        deployed_config = self.deployer.get_agent_config()
        if deployed_config:
            # Update our current config with the deployed state
            # This catches any external modifications or deployment drift
            print(f"✓ Using deployed agent config for analysis")
            # Merge deployed config into current config (deployed takes precedence)
            self.current_config.update(deployed_config)
            # Update current_prompt to match deployed state
            self.current_prompt = deployed_config.get("nl2sql_prompt", self.current_prompt)
        else:
            print(f"⚠ Could not fetch deployed config, using in-memory config")

        # Step 3: Extract successful test cases for pattern insights
        # CRITICAL: Both failures and results are from TRAINING SET ONLY
        # This ensures no test data leakage into the optimization process
        successes = [r for r in results if r.get('passed', False)]

        # Validation: Ensure we're not accidentally analyzing test data
        # Test data should never reach this function
        for failure in failures[:5]:  # Spot check first 5
            assert 'question' in failure, "Invalid failure format - missing 'question' field"
        for success in successes[:5]:  # Spot check first 5
            assert 'question' in success, "Invalid success format - missing 'question' field"

        print(f"Analyzing {len(failures)} TRAINING failures and {len(successes)} TRAINING successes")

        # Step 2: Initialize analyzers if needed
        # Use Vertex AI-compatible location for AI components
        vertex_location = get_vertex_ai_location(self.location)

        if not self.config_analyzer:
            print("Initializing configuration field analyzer...")
            self.config_analyzer = ConfigFieldAnalyzer(
                project_id=self.project_id,
                location=vertex_location
            )

        if not self.improver:
            print("Initializing AI prompt improver...")
            self.improver = PromptImprover(
                project_id=self.project_id,
                location=vertex_location
            )

        # Step 3: Analyze which config fields should be modified
        print("\nAnalyzing configuration fields...")
        recommendations = self.config_analyzer.analyze_config_improvements(
            failures=failures,
            current_config=self.current_config,
            successes=successes,
            previous_metrics=previous_metrics  # NEW: Pass trajectory context
        )

        # Step 3: Display field recommendations
        field_recs = recommendations.get("field_recommendations", {})
        fields_to_modify = [
            field for field, rec in field_recs.items()
            if rec.get("should_modify", False)
        ]

        if not fields_to_modify:
            print("\n✓ No configuration changes recommended")
            return self.current_prompt, "No changes recommended"

        print(f"\n📋 Recommended Configuration Changes ({len(fields_to_modify)} fields):\n")

        # Sort by priority (highest first)
        sorted_fields = sorted(
            fields_to_modify,
            key=lambda f: field_recs[f].get("priority", 1),
            reverse=True
        )

        for field in sorted_fields:
            rec = field_recs[field]
            priority = rec.get("priority", 1)
            rationale = rec.get("rationale", "No rationale")
            priority_label = "🔴 CRITICAL" if priority >= 4 else "🟡 MEDIUM" if priority >= 3 else "🟢 LOW"
            print(f"{priority_label} {field}:")
            print(f"  Reason: {rationale[:150]}{'...' if len(rationale) > 150 else ''}\n")

        # Step 4: Improve high-priority fields using AI
        improved_config = self.current_config.copy()
        change_descriptions = []

        # Focus on nl2sql_prompt with PromptImprover (backward compatible)
        if "nl2sql_prompt" in fields_to_modify:
            print("\n--- Improving nl2sql_prompt ---")
            suggested_prompt = self.improver.analyze_failures(
                failures=failures,
                current_prompt=self.current_prompt,
                successes=successes,
                previous_metrics=previous_metrics  # NEW: Pass trajectory context
            )
            improved_prompt, prompt_change_desc = self.improver.present_suggestions_to_user(
                current_prompt=self.current_prompt,
                suggested_prompt=suggested_prompt,
                auto_accept=self.auto_accept
            )

            if improved_prompt != self.current_prompt:
                improved_config["nl2sql_prompt"] = improved_prompt
                change_descriptions.append(f"nl2sql_prompt: {prompt_change_desc}")

        # Apply AI suggestions for other fields (if should_modify and has suggested_value)
        for field in sorted_fields:
            if field == "nl2sql_prompt":
                continue  # Already handled above

            rec = field_recs[field]
            suggested_value = rec.get("suggested_value", "")

            if suggested_value and rec.get("priority", 1) >= 3:  # Only apply medium+ priority
                if self.auto_accept:
                    # Auto-apply in auto-accept mode
                    improved_config[field] = suggested_value
                    change_descriptions.append(
                        f"{field}: {rec.get('rationale', 'Updated')[:100]}"
                    )
                    print(f"\n✓ Auto-applied: {field}")
                else:
                    # Ask user to review
                    print(f"\n--- Suggested change for {field} ---")
                    print(f"Rationale: {rec.get('rationale', 'No rationale')}")
                    print(f"\nSuggested value (first 500 chars):")
                    print(f"{str(suggested_value)[:500]}...")
                    choice = input(f"\nApply this change? (y/n): ").strip().lower()
                    if choice == 'y':
                        improved_config[field] = suggested_value
                        change_descriptions.append(
                            f"{field}: {rec.get('rationale', 'Updated')[:100]}"
                        )
                        print(f"✓ Applied: {field}")

        # Step 5: Update current config and return
        self.current_config = improved_config
        full_change_desc = "; ".join(change_descriptions) if change_descriptions else "No changes applied"

        # Return prompt for backward compatibility
        return improved_config.get("nl2sql_prompt", self.current_prompt), full_change_desc

    def _ask_to_continue(self, iteration: int) -> bool:
        """Ask user if they want to run another iteration (or auto-continue in auto-accept mode)."""
        if iteration >= self.max_iterations:
            print(f"\nMaximum iterations ({self.max_iterations}) reached.")
            return False

        if self.auto_accept:
            print(f"\n{'='*80}")
            print("AUTO-ACCEPT MODE: Continuing to next iteration automatically")
            print(f"{'='*80}\n")
            return True

        print(f"\n{'='*80}")
        choice = input(f"Run another iteration? (y/n): ").strip().lower()
        return choice == 'y'

    def _get_current_config(self) -> Dict[str, Any]:
        """Get current agent configuration with all fields."""
        return self.current_config.copy()

    def _get_prompt_changes(self, iteration: int) -> str:
        """Get description of configuration changes for this iteration."""
        if iteration == 1:
            return "Initial configuration"
        return self.config_changes_description if hasattr(self, 'config_changes_description') else self.prompt_change_description

    def _save_config_snapshot(self, iteration: int, config: Dict[str, Any], config_type: str = "final"):
        """
        Save configuration to separate file for version control.

        Args:
            iteration: Iteration number
            config: Configuration to save
            config_type: Type of config ("final" or "suggested")
        """
        config_dir = self.run_dir / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / f"config_iteration_{iteration}_{config_type}_{self.run_timestamp}.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"  Saved {config_type} config: {config_path}")

    def _handle_authorization_error(self, error: AgentAuthorizationError):
        """
        Handle agent authorization errors by guiding user to authorize.

        Args:
            error: The AgentAuthorizationError that was raised
        """
        print(f"\n{'='*80}")
        print("⚠️  AGENT AUTHORIZATION REQUIRED")
        print(f"{'='*80}\n")

        print(f"The agent requires OAuth authorization to access BigQuery.")
        print(f"This is a one-time setup per agent.\n")

        print(f"Agent Details:")
        print(f"  Agent ID: {error.agent_id}")
        print(f"  Project: {error.project_id}")
        print(f"  Location: {error.location}")
        print(f"  Engine: {error.engine_id}\n")

        print(f"{'='*80}")
        print("AUTHORIZATION STEPS")
        print(f"{'='*80}\n")

        print("1. Set the DIA_AGENT_ID environment variable:")
        print(f"   export DIA_AGENT_ID={error.agent_id}\n")

        print("2. Run the authorization script:")
        print(f"   python scripts/authorize_agent.py\n")

        print("3. The script will:")
        print("   • Query the agent to trigger authorization")
        print("   • Extract the OAuth authorization URL")
        print("   • Display the URL for you to visit\n")

        print("4. Visit the URL in your browser and:")
        print("   • Sign in with your Google account")
        print("   • Grant BigQuery access permissions")
        print("   • Complete the authorization flow\n")

        print("5. After authorizing, re-run the optimization:")
        print(f"   dia-harness optimize --config-file configs/baseline_config.json --golden-set {self.golden_set_path}\n")

        print(f"{'='*80}")
        print("NOTE: Authorization persists across runs - you only need to do this once per agent.")
        print(f"{'='*80}\n")

    def _display_final_summary(self):
        """Display final summary of optimization trajectory."""
        print(f"\n{'='*80}")
        print("OPTIMIZATION COMPLETE")
        print(f"{'='*80}\n")

        summary = self.tracker.get_trajectory_summary()

        print(f"Total Iterations: {summary['total_iterations']}")
        print(f"\nBest Iteration: #{summary['best_iteration']['iteration']} "
              f"({summary['best_iteration']['accuracy']}% accuracy)")
        print(f"Worst Iteration: #{summary['worst_iteration']['iteration']} "
              f"({summary['worst_iteration']['accuracy']}% accuracy)")

        print(f"\nAccuracy Progression: {summary['accuracy_progression']}")
        print(f"Overall Improvement: {summary['overall_improvement']}%")

        print(f"\nTrajectory saved to: {self.tracker.output_path}")
        print(f"Agent ID: {self.agent_id}")

    def _generate_artifacts(self):
        """Generate visualization charts and comprehensive report."""
        print(f"\n{'='*80}")
        print("GENERATING ARTIFACTS")
        print(f"{'='*80}\n")

        try:
            # Import visualizer and report generator
            from .visualizer import TrajectoryVisualizer
            from .report_generator import OptimizationReportGenerator

            # Generate charts
            print("Generating visualization charts...")
            charts_dir = self.run_dir / "charts"
            visualizer = TrajectoryVisualizer(
                trajectory_data=self.tracker.history,
                output_dir=str(charts_dir)
            )
            chart_paths_dict = visualizer.generate_all_charts()

            print("\nCharts generated:")
            for name, path in chart_paths_dict.items():
                if path:
                    print(f"  ✓ {name}: {path}")

            # Convert chart paths dict to list (filter out None values)
            chart_paths_list = [path for path in chart_paths_dict.values() if path is not None]

            # Generate comprehensive report
            print("\nGenerating comprehensive markdown report...")
            report_gen = OptimizationReportGenerator(output_dir=str(self.run_dir))
            report_path = report_gen.generate_report(
                trajectory_history=self.tracker.history,
                chart_paths=chart_paths_list,
                agent_id=self.agent_id
            )

            print(f"\n{'='*80}")
            print(f"📊 Full optimization report: {report_path}")
            print(f"📈 Charts directory: {charts_dir}")
            print(f"{'='*80}\n")

        except ImportError as e:
            print(f"Warning: Could not generate artifacts: {e}")
            print("Charts and reports require matplotlib and seaborn.")
            print("Install with: uv pip install matplotlib seaborn")
        except Exception as e:
            print(f"Warning: Error generating artifacts: {e}")
            print("Continuing without visualization...")
