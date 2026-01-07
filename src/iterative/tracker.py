"""
TrajectoryTracker: Manages iteration history for closed-loop optimization.

Stores rich detail for each iteration including:
- Configuration (prompt, params)
- Test results (all evaluations)
- Metrics (accuracy, exact match, semantic equivalence, failures)
- Failures (detailed breakdown)
- Prompt changes (description of modifications)
"""

import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime


class TrajectoryTracker:
    """
    Tracks the trajectory of iterative agent optimization.

    Manages a history of iterations with full configuration, results, and metrics.
    Provides comparison capabilities to analyze improvements or regressions.
    """

    def __init__(self, agent_name: str = "baseline", output_path: str = "results/trajectory_history.json"):
        """
        Initialize tracker.

        Args:
            agent_name: Name of the agent being optimized
            output_path: Path to save trajectory history JSON
        """
        self.agent_name = agent_name
        self.output_path = output_path
        self.history = {
            "agent_name": agent_name,
            "start_time": datetime.utcnow().isoformat(),
            "iterations": []
        }

        # Load existing history if available
        if Path(output_path).exists():
            try:
                with open(output_path, 'r') as f:
                    self.history = json.load(f)
                print(f"Loaded existing trajectory with {len(self.history['iterations'])} iterations")
            except Exception as e:
                print(f"Could not load existing trajectory: {e}. Starting fresh.")

    def add_iteration(
        self,
        iteration_num: int,
        config: Dict[str, Any],
        results: List[Dict],
        metrics: Dict[str, Any],
        failures: List[Dict],
        prompt_changes: str = ""
    ):
        """
        Add an iteration to the trajectory.

        Args:
            iteration_num: Iteration number (1, 2, 3, ...)
            config: Agent configuration (nl2sql_prompt, params, etc.)
            results: Full test results (list of dicts from TestRunner)
            metrics: Calculated metrics (accuracy, exact_match, etc.)
            failures: List of failed test cases with details
            prompt_changes: Description of what changed in the prompt
        """
        iteration_record = {
            "iteration": iteration_num,
            "timestamp": datetime.utcnow().isoformat(),
            "config": config,
            "results": results,
            "metrics": metrics,
            "failures": failures,
            "prompt_changes": prompt_changes
        }

        self.history["iterations"].append(iteration_record)

    def get_last_iteration(self) -> Optional[Dict]:
        """
        Get the most recent iteration record.

        Returns:
            Dict with iteration data, or None if no iterations exist
        """
        if not self.history["iterations"]:
            return None
        return self.history["iterations"][-1]

    def get_iteration(self, iteration_num: int) -> Optional[Dict]:
        """
        Get a specific iteration by number.

        Args:
            iteration_num: Iteration number to retrieve

        Returns:
            Dict with iteration data, or None if not found
        """
        for iteration in self.history["iterations"]:
            if iteration["iteration"] == iteration_num:
                return iteration
        return None

    def compare_iterations(self, iter1_num: int, iter2_num: int) -> Dict[str, Any]:
        """
        Compare two iterations to show improvements/regressions.

        Args:
            iter1_num: First iteration number
            iter2_num: Second iteration number

        Returns:
            Dict with comparison results:
                - accuracy_delta: Change in accuracy percentage
                - new_failures: Questions that started failing
                - resolved_issues: Questions that now pass
                - metrics_comparison: Side-by-side metrics
        """
        iter1 = self.get_iteration(iter1_num)
        iter2 = self.get_iteration(iter2_num)

        if not iter1 or not iter2:
            return {"error": "One or both iterations not found"}

        # Calculate accuracy delta
        accuracy_delta = iter2["metrics"]["accuracy"] - iter1["metrics"]["accuracy"]

        # Find new failures and resolved issues
        iter1_failed_ids = {f["question_id"] for f in iter1["failures"]}
        iter2_failed_ids = {f["question_id"] for f in iter2["failures"]}

        iter1_passed_ids = {r["question_id"] for r in iter1["results"] if r.get("is_match") or ("EQUIVALENT" in str(r.get("explanation", "")).upper())}
        iter2_passed_ids = {r["question_id"] for r in iter2["results"] if r.get("is_match") or ("EQUIVALENT" in str(r.get("explanation", "")).upper())}

        new_failures = iter2_failed_ids - iter1_failed_ids
        resolved_issues = iter1_failed_ids - iter2_failed_ids

        # Get question details for new failures and resolved issues
        new_failure_details = [
            {
                "question_id": f["question_id"],
                "question": f["question"],
                "issue": f["issue"]
            }
            for f in iter2["failures"] if f["question_id"] in new_failures
        ]

        resolved_issue_details = [
            {
                "question_id": f["question_id"],
                "question": f["question"],
                "issue": f["issue"]
            }
            for f in iter1["failures"] if f["question_id"] in resolved_issues
        ]

        return {
            "accuracy_delta": round(accuracy_delta, 2),
            "new_failures": new_failure_details,
            "resolved_issues": resolved_issue_details,
            "metrics_comparison": {
                f"iteration_{iter1_num}": iter1["metrics"],
                f"iteration_{iter2_num}": iter2["metrics"]
            }
        }

    def get_trajectory_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the entire trajectory.

        Returns:
            Dict with:
                - total_iterations: Number of iterations
                - best_iteration: Iteration with highest accuracy
                - worst_iteration: Iteration with lowest accuracy
                - accuracy_progression: List of accuracy values over time
                - overall_improvement: Delta from first to last iteration
        """
        if not self.history["iterations"]:
            return {"error": "No iterations recorded"}

        iterations = self.history["iterations"]
        accuracy_progression = [it["metrics"]["accuracy"] for it in iterations]

        best_iter = max(iterations, key=lambda x: x["metrics"]["accuracy"])
        worst_iter = min(iterations, key=lambda x: x["metrics"]["accuracy"])

        overall_improvement = accuracy_progression[-1] - accuracy_progression[0]

        return {
            "total_iterations": len(iterations),
            "best_iteration": {
                "iteration": best_iter["iteration"],
                "accuracy": best_iter["metrics"]["accuracy"]
            },
            "worst_iteration": {
                "iteration": worst_iter["iteration"],
                "accuracy": worst_iter["metrics"]["accuracy"]
            },
            "accuracy_progression": accuracy_progression,
            "overall_improvement": round(overall_improvement, 2)
        }

    def save(self, path: str = None):
        """
        Save trajectory history to JSON file.

        Args:
            path: Optional custom path (defaults to self.output_path)
        """
        save_path = path or self.output_path

        # Ensure directory exists
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w') as f:
            json.dump(self.history, f, indent=2)

        print(f"Trajectory saved to {save_path}")

    def load(self, path: str = None):
        """
        Load trajectory history from JSON file.

        Args:
            path: Optional custom path (defaults to self.output_path)
        """
        load_path = path or self.output_path

        if not Path(load_path).exists():
            raise FileNotFoundError(f"Trajectory file not found: {load_path}")

        with open(load_path, 'r') as f:
            self.history = json.load(f)

        print(f"Trajectory loaded from {load_path} with {len(self.history['iterations'])} iterations")
