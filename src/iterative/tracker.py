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

    def __init__(self, agent_name: str = "baseline", agent_id: str = None, output_path: str = None, timestamp: str = None):
        """
        Initialize tracker.

        Args:
            agent_name: Name of the agent being optimized
            agent_id: Numeric agent ID (optional)
            output_path: Path to save trajectory history JSON (auto-generated with timestamp if None)
            timestamp: Timestamp string to use for filename (auto-generated if None)
        """
        self.agent_name = agent_name
        self.agent_id = agent_id

        # Generate timestamped filename if output_path not provided
        if output_path is None:
            if timestamp is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"results/trajectory_history_{timestamp}.json"

        self.output_path = output_path
        self.timestamp = timestamp
        self.history = {
            "agent_name": agent_name,
            "agent_id": agent_id,
            "start_time": datetime.utcnow().isoformat(),
            "iterations": []
        }

        # Only load existing history if a specific path was provided (not auto-generated)
        # For timestamped runs, always start fresh
        if timestamp is None and Path(output_path).exists():
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
        prompt_changes: str = "",
        suggested_config: Optional[Dict[str, Any]] = None,
        config_approved: bool = True,
        deployment_success: bool = True,
        test_results: Optional[List[Dict]] = None,
        test_metrics: Optional[Dict[str, Any]] = None
    ):
        """
        Add an iteration to the trajectory.

        Args:
            iteration_num: Iteration number (1, 2, 3, ...)
            config: Agent configuration (nl2sql_prompt, params, etc.)
            results: Full test results from training set (list of dicts from TestRunner)
            metrics: Calculated metrics from training set (accuracy, exact_match, etc.)
            failures: List of failed test cases with details
            prompt_changes: Description of what changed in the prompt
            suggested_config: AI-suggested configuration (before user approval)
            config_approved: Whether user approved the suggested config (or auto-accepted)
            deployment_success: Whether deployment to agent succeeded
            test_results: Optional results from held-out test set
            test_metrics: Optional metrics from held-out test set
        """
        # Build evaluation structure for report generator compatibility
        evaluation = {
            "train": self._convert_metrics_to_eval_format(metrics, failures)
        }

        # Add test evaluation if provided
        if test_metrics is not None:
            test_failures = []  # Test failures are already in test_results
            evaluation["test"] = self._convert_metrics_to_eval_format(test_metrics, test_failures)

        iteration_record = {
            "iteration": iteration_num,
            "timestamp": datetime.utcnow().isoformat(),
            "configuration": config,  # Final applied configuration
            "suggested_configuration": suggested_config,  # AI suggestion (before approval)
            "config_approved": config_approved,  # Whether user approved
            "deployment_success": deployment_success,  # Whether deployment worked
            "evaluation": evaluation,
            "prompt_changes": prompt_changes,
            # Keep raw data for backward compatibility and detailed analysis
            "results": results,
            "metrics": metrics,
            "failures": failures
        }

        # Add test set data if provided
        if test_results is not None:
            iteration_record["test_results"] = test_results
        if test_metrics is not None:
            iteration_record["test_metrics"] = test_metrics

        self.history["iterations"].append(iteration_record)

    def _convert_metrics_to_eval_format(self, metrics: Dict[str, Any], failures: List[Dict]) -> Dict[str, Any]:
        """
        Convert metrics dict to evaluation format expected by report generator.

        Args:
            metrics: Dict with accuracy, total, etc. (may have nested mean/std/values)
            failures: List of failure dicts

        Returns:
            Dict in evaluation format
        """
        # Extract accuracy - handle both simple float and nested dict with mean/values
        if isinstance(metrics.get("accuracy"), dict):
            # New format with repeat measurements
            accuracy = metrics["accuracy"]["mean"] / 100.0  # Convert percentage to decimal
            repeat_measurements = metrics["accuracy"].get("values", [])
            repeat_measurements = [v / 100.0 for v in repeat_measurements]  # Convert to decimals
        else:
            # Old format with simple value
            accuracy = metrics.get("accuracy", 0.0)
            if accuracy > 1.0:  # If it's a percentage
                accuracy = accuracy / 100.0
            repeat_measurements = None

        total_cases = metrics.get("total", 0)
        correct = int(accuracy * total_cases) if total_cases > 0 else 0

        eval_format = {
            "accuracy": accuracy,
            "total_cases": total_cases,
            "correct": correct,
            "failures": failures
        }

        # Add repeat measurements if available
        if repeat_measurements and len(repeat_measurements) > 1:
            eval_format["repeat_measurements"] = repeat_measurements

        return eval_format

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

    def _extract_accuracy(self, metrics: Dict) -> float:
        """
        Extract accuracy value whether it's a float or dict (from repeats).

        Prefers question_level_accuracy if available (treats API errors as missing data).
        Falls back to repeat-level mean accuracy otherwise.

        Args:
            metrics: Metrics dict with accuracy as float or dict

        Returns:
            float: Accuracy as a percentage (0-100)
        """
        # Prefer question-level accuracy (errors treated as missing data)
        if "question_level_accuracy" in metrics:
            return metrics["question_level_accuracy"]

        # Fallback to standard accuracy
        acc = metrics.get("accuracy", 0.0)
        if isinstance(acc, dict):
            return acc.get("mean", 0.0)
        return acc

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
        accuracy_progression = [self._extract_accuracy(it["metrics"]) for it in iterations]

        best_iter = max(iterations, key=lambda x: self._extract_accuracy(x["metrics"]))
        worst_iter = min(iterations, key=lambda x: self._extract_accuracy(x["metrics"]))

        overall_improvement = accuracy_progression[-1] - accuracy_progression[0]

        return {
            "total_iterations": len(iterations),
            "best_iteration": {
                "iteration": best_iter["iteration"],
                "accuracy": self._extract_accuracy(best_iter["metrics"])
            },
            "worst_iteration": {
                "iteration": worst_iter["iteration"],
                "accuracy": self._extract_accuracy(worst_iter["metrics"])
            },
            "accuracy_progression": accuracy_progression,
            "overall_improvement": round(overall_improvement, 2)
        }

    def get_top_n_by_accuracy(self, n: int = 20, max_prompt_length: int = 500) -> List[Dict[str, Any]]:
        """
        Get top N iterations by accuracy, sorted ascending (worst to best).

        This aligns with OPRO research: showing best prompts at the end leverages
        recency bias - LLMs pay more attention to the end of context.

        Args:
            n: Number of top iterations to return (default: 20 per OPRO)
            max_prompt_length: Maximum chars per prompt for context efficiency (default: 500)

        Returns:
            List of dicts sorted by accuracy (ascending), each containing:
                - prompt (str): Truncated nl2sql_prompt
                - accuracy (float): Accuracy percentage
                - iteration (int): Iteration number
                - prompt_preview (str): First 100 chars for quick scanning
        """
        if not self.history["iterations"]:
            return []

        iterations = self.history["iterations"]

        # Extract (prompt, accuracy, iteration) tuples
        trajectory_pairs = []
        for it in iterations:
            prompt = it.get("configuration", {}).get("nl2sql_prompt", "")
            accuracy = self._extract_accuracy(it["metrics"])
            iteration_num = it.get("iteration", 0)

            # Truncate prompt to manage context length
            truncated_prompt = prompt[:max_prompt_length] + ("..." if len(prompt) > max_prompt_length else "")

            trajectory_pairs.append({
                "prompt": truncated_prompt,
                "full_prompt": prompt,  # Keep full for reference
                "accuracy": accuracy,
                "iteration": iteration_num,
                "prompt_preview": prompt[:100] + ("..." if len(prompt) > 100 else "")
            })

        # Sort by accuracy (ascending: worst to best)
        sorted_trajectory = sorted(trajectory_pairs, key=lambda x: x["accuracy"])

        # Take top N (best scoring)
        top_n = sorted_trajectory[-n:] if len(sorted_trajectory) > n else sorted_trajectory

        return top_n

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
