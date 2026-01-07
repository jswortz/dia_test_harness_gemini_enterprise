"""
SingleAgentEvaluator: Wrapper for single-agent evaluation with metrics calculation.

Integrates:
- TestRunner (test execution)
- SQLComparator (exact SQL matching)
- JudgementModel (LLM-based semantic equivalence)
- Metrics calculation (accuracy, failures, etc.)
"""

from typing import List, Dict, Any, Tuple
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from evaluation.runner import TestRunner
from evaluation.evaluator import SQLComparator, JudgementModel
from evaluation.agent_client import AgentClient
from evaluation.data_loader import GoldenSetLoader


class SingleAgentEvaluator:
    """
    Evaluates a single Data Insights Agent against a golden set.

    Provides:
    - Simplified interface for running evaluations
    - Automatic metrics calculation
    - Failure extraction for prompt improvement
    """

    def __init__(
        self,
        agent_id: str,
        project_id: str,
        location: str,
        engine_id: str,
        output_path: str = "results/eval_results.jsonl"
    ):
        """
        Initialize evaluator.

        Args:
            agent_id: Agent ID to evaluate
            project_id: Google Cloud project ID
            location: Location (e.g., "global")
            engine_id: Discovery Engine ID
            output_path: Path to save evaluation results
        """
        self.agent_id = agent_id
        self.project_id = project_id
        self.location = location
        self.engine_id = engine_id
        self.output_path = output_path

        # Initialize components
        self.loader = GoldenSetLoader()
        self.client = AgentClient(project_id, location, engine_id, agent_id)
        self.comparator = SQLComparator()
        self.judge = JudgementModel(project_id, location)

        # Create TestRunner
        self.runner = TestRunner(
            loader=self.loader,
            client=self.client,
            comparator=self.comparator,
            judge=self.judge,
            output_path=output_path
        )

    def evaluate(self, golden_set_path: str) -> Tuple[List[Dict], Dict[str, Any], List[Dict]]:
        """
        Run evaluation against golden set.

        Args:
            golden_set_path: Path to golden set file (JSON/CSV/Excel)

        Returns:
            Tuple of:
                - results: List of detailed test results
                - metrics: Dict with accuracy, exact_match, failures, etc.
                - failures: List of failed test cases with details
        """
        print(f"\n=== Running Evaluation ===")
        print(f"Agent ID: {self.agent_id}")
        print(f"Golden Set: {golden_set_path}\n")

        # Run tests
        self.runner.run(golden_set_path)

        # Get results
        results = self.runner.results

        # Calculate metrics
        metrics = self.runner.calculate_metrics(results)

        # Extract failures
        failures = self.runner.extract_failures(results)

        # Display summary
        self._display_summary(metrics, failures)

        return results, metrics, failures

    def _display_summary(self, metrics: Dict[str, Any], failures: List[Dict]):
        """Display evaluation summary to user."""
        print(f"\n=== Evaluation Complete ===")
        print(f"Total Tests: {metrics['total']}")
        print(f"Exact Matches: {metrics['exact_match']}")
        print(f"Semantically Equivalent: {metrics['semantically_equivalent']}")
        print(f"Failures: {metrics['failures']}")
        print(f"Errors: {metrics['error_count']}")
        print(f"\nAccuracy: {metrics['accuracy']}%")

        if failures:
            print(f"\n=== Failed Questions ({len(failures)}) ===")
            for i, failure in enumerate(failures, 1):
                print(f"\n{i}. {failure['question']}")
                print(f"   Issue: {failure['issue']}")
                if failure.get('explanation'):
                    # Truncate long explanations
                    explanation = failure['explanation']
                    if len(explanation) > 200:
                        explanation = explanation[:200] + "..."
                    print(f"   Explanation: {explanation}")
