"""
IterativeOptimizer: Main orchestrator for closed-loop agent optimization.

Coordinates:
- Agent deployment (initial + PATCH updates)
- Evaluation against golden set
- Trajectory tracking
- Prompt improvement suggestions
- User interaction for iteration control
"""

from typing import Dict, Any, Optional
from .deployer import SingleAgentDeployer
from .evaluator import SingleAgentEvaluator
from .tracker import TrajectoryTracker
from .prompt_improver import PromptImprover
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from evaluation.agent_client import AgentAuthorizationError


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
        max_iterations: int = 10
    ):
        """
        Initialize optimizer.

        Args:
            config: Agent configuration (name, nl2sql_prompt, params, description)
            golden_set_path: Path to golden set file (JSON/CSV/Excel)
            project_id: Google Cloud project ID
            location: Location (e.g., "global")
            engine_id: Discovery Engine ID
            dataset_id: BigQuery dataset ID
            max_iterations: Maximum number of iterations (safety limit)
        """
        self.config = config
        self.golden_set_path = golden_set_path
        self.project_id = project_id
        self.location = location
        self.engine_id = engine_id
        self.dataset_id = dataset_id
        self.max_iterations = max_iterations

        # Initialize components (will be created after deployment)
        self.deployer: Optional[SingleAgentDeployer] = None
        self.evaluator: Optional[SingleAgentEvaluator] = None
        self.tracker: Optional[TrajectoryTracker] = None
        self.improver: Optional[PromptImprover] = None

        self.agent_id: Optional[str] = None
        self.current_prompt: str = ""
        self.current_params: Dict[str, Any] = {}

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
        print(f"\n{'='*80}")
        print("ITERATIVE AGENT OPTIMIZATION")
        print(f"{'='*80}\n")
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
                # Step 1: Deploy or update agent
                if iteration == 1:
                    self._deploy_initial()
                else:
                    # Agent already exists, PATCH will be done after user approves new prompt
                    # which happens at the end of the previous iteration
                    pass

                # Step 2: Run evaluation
                results, metrics, failures = self._run_evaluation()

                # Step 3: Track in trajectory
                prompt_changes = self._get_prompt_changes(iteration)
                self.tracker.add_iteration(
                    iteration_num=iteration,
                    config=self._get_current_config(),
                    results=results,
                    metrics=metrics,
                    failures=failures,
                    prompt_changes=prompt_changes
                )
                self.tracker.save()

                # Step 4: Display results with comparison
                self._display_results(iteration, metrics, failures)

                # Step 5: Check if perfect score
                if metrics['accuracy'] >= 100.0:
                    print(f"\n{'='*80}")
                    print("PERFECT SCORE ACHIEVED!")
                    print(f"{'='*80}\n")
                    print("All tests passed. Optimization complete.")
                    break

                # Step 6: Analyze failures and suggest improvements
                if failures:
                    improved_prompt, change_description = self._improve_prompt(failures)

                    if improved_prompt != self.current_prompt:
                        # Update prompt for next iteration
                        self.current_prompt = improved_prompt
                        self.prompt_change_description = change_description

                        # PATCH agent with new prompt
                        print("\nApplying prompt changes to agent...")
                        success = self.deployer.update_prompt(improved_prompt, self.current_params)
                        if not success:
                            print("Warning: Failed to update agent. Will retry in next iteration.")
                    else:
                        print("\nNo prompt changes. Keeping current prompt.")

                # Step 7: Ask user to continue
                if not self._ask_to_continue(iteration):
                    break

                iteration += 1

            except AgentAuthorizationError as e:
                # Agent requires OAuth authorization - stop optimization immediately
                self._handle_authorization_error(e)
                return  # Exit optimization loop

        # Final summary
        self._display_final_summary()

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
            output_path="results/trajectory_history.json"
        )

        # Initialize prompt improver lazily (when first failure occurs)
        # to avoid blocking during initialization
        # self.improver will be created in _improve_prompt() if needed

        # Initialize prompt and params from config
        self.current_prompt = self.config.get("nl2sql_prompt", "")
        self.current_params = self.config.get("params", {})
        self.prompt_change_description = "Initial configuration"

    def _deploy_initial(self):
        """Deploy agent for the first time."""
        print("Deploying agent...")
        self.agent_id = self.deployer.deploy_initial(self.config)

        # Create evaluator now that we have agent_id
        self.evaluator = SingleAgentEvaluator(
            agent_id=self.agent_id,
            project_id=self.project_id,
            location=self.location,
            engine_id=self.engine_id,
            output_path=f"results/eval_iteration_1.jsonl"
        )

    def _run_evaluation(self) -> tuple:
        """Run evaluation and return results, metrics, failures."""
        return self.evaluator.evaluate(self.golden_set_path)

    def _display_results(self, iteration: int, metrics: Dict[str, Any], failures: list):
        """Display results with comparison to previous iteration."""
        print(f"\n{'='*80}")
        print(f"ITERATION {iteration} RESULTS")
        print(f"{'='*80}\n")

        print(f"Accuracy: {metrics['accuracy']}% ({metrics['total'] - metrics['failures']}/{metrics['total']} tests passed)")
        print(f"  ✓ Exact match: {metrics['exact_match']}")
        print(f"  ✓ Semantically equivalent: {metrics['semantically_equivalent']}")
        print(f"  ✗ Failures: {metrics['failures']}")
        if metrics['error_count'] > 0:
            print(f"  ⚠ Errors: {metrics['error_count']}")

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

    def _improve_prompt(self, failures: list) -> tuple:
        """Analyze failures and get improved prompt from user."""
        print(f"\n{'='*80}")
        print("PROMPT IMPROVEMENT")
        print(f"{'='*80}\n")

        # Create improver lazily if not already created
        if not self.improver:
            print("Initializing AI prompt analyzer...")
            self.improver = PromptImprover(project_id=self.project_id, location=self.location)

        # Generate suggestions
        suggested_prompt = self.improver.analyze_failures(failures, self.current_prompt)

        # Present to user and get decision
        improved_prompt, change_description = self.improver.present_suggestions_to_user(
            current_prompt=self.current_prompt,
            suggested_prompt=suggested_prompt
        )

        return improved_prompt, change_description

    def _ask_to_continue(self, iteration: int) -> bool:
        """Ask user if they want to run another iteration."""
        if iteration >= self.max_iterations:
            print(f"\nMaximum iterations ({self.max_iterations}) reached.")
            return False

        print(f"\n{'='*80}")
        choice = input(f"Run another iteration? (y/n): ").strip().lower()
        return choice == 'y'

    def _get_current_config(self) -> Dict[str, Any]:
        """Get current agent configuration."""
        return {
            "name": self.config.get("name", "baseline"),
            "nl2sql_prompt": self.current_prompt,
            "params": self.current_params,
            "description": self.config.get("description", "")
        }

    def _get_prompt_changes(self, iteration: int) -> str:
        """Get description of prompt changes for this iteration."""
        if iteration == 1:
            return "Initial configuration"
        return self.prompt_change_description

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

        print(f"\nTrajectory saved to: results/trajectory_history.json")
        print(f"Agent ID: {self.agent_id}")
