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
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import random

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from evaluation.runner import TestRunner
from evaluation.evaluator import SQLComparator, JudgementModel
from evaluation.agent_client import AgentClient
from evaluation.data_loader import GoldenSetLoader


def get_vertex_ai_location(agent_location: str) -> str:
    """
    Maps agent location to a valid Vertex AI region.
    
    Agent locations like 'us', 'eu', 'asia' need to be mapped to specific
    Vertex AI regions like 'us-central1', 'europe-west1', etc.
    """
    location_map = {
        'us': 'us-central1',
        'eu': 'europe-west1',
        'asia': 'asia-southeast1',
        'global': 'global',
    }
    
    # If it's already a specific region (e.g., us-central1), return it
    if agent_location in location_map:
        return location_map[agent_location]
    else:
        # Assume it's already a valid region
        return agent_location


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
        output_path: str = None,
        timestamp: str = None,
        max_workers: int = 10,
        schema_description: str = None,
        use_flexible_scoring: bool = None
    ):
        """
        Initialize evaluator.

        Args:
            agent_id: Agent ID to evaluate
            project_id: Google Cloud project ID
            location: Location (e.g., "global")
            engine_id: Discovery Engine ID
            output_path: Path to save evaluation results (auto-generated with timestamp if None)
            timestamp: Timestamp string for filenames (auto-generated if None)
            max_workers: Maximum number of parallel workers for test execution (default: 10)
            schema_description: Database schema description for context in judgement (optional but recommended)
            use_flexible_scoring: Use 100-point flexible rubric instead of binary pass/fail
                                  (default: from USE_FLEXIBLE_SCORING env var or True)
        """
        self.agent_id = agent_id
        self.project_id = project_id
        self.location = location
        self.engine_id = engine_id
        self.max_workers = max_workers
        self.schema_description = schema_description or ""

        # Determine flexible scoring setting
        if use_flexible_scoring is None:
            use_flexible_scoring = os.getenv("USE_FLEXIBLE_SCORING", "true").lower() == "true"
        self.use_flexible_scoring = use_flexible_scoring

        # Generate timestamped filename if not provided
        if output_path is None:
            from datetime import datetime
            if timestamp is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"results/eval_{timestamp}.jsonl"

        self.output_path = output_path
        self.timestamp = timestamp

        # Initialize components
        self.loader = GoldenSetLoader()

        # Configure connection pool size to accommodate parallel workers
        # Add buffer of 20 connections to handle retries and overhead
        max_connections = max(100, max_workers + 20)

        self.client = AgentClient(
            project_id,
            location,
            engine_id,
            agent_id,
            max_connections=max_connections
        )
        self.comparator = SQLComparator()
        # Use Vertex AI-compatible location for the judge model
        vertex_location = get_vertex_ai_location(location)
        self.judge = JudgementModel(project_id, vertex_location)

        # Create TestRunner with schema description and flexible scoring option
        self.runner = TestRunner(
            loader=self.loader,
            client=self.client,
            comparator=self.comparator,
            judge=self.judge,
            output_path=output_path,
            schema_description=self.schema_description,
            use_flexible_scoring=self.use_flexible_scoring
        )

        # Thread-safe lock for result aggregation
        self._results_lock = threading.Lock()

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

    def _run_single_test(
        self,
        test_case: Dict,
        repeat_num: int,
        test_idx: int,
        max_retries: int = 3,
        initial_backoff: float = 1.0
    ) -> Dict:
        """
        Run a single test case with isolated session (for parallel execution).

        Includes exponential backoff retry logic for transient errors.

        Args:
            test_case: Dict with 'nl_question', 'expected_sql', 'question_id'
            repeat_num: Which repeat this is (1, 2, 3, ...)
            test_idx: Index of test in golden set (for ordering)
            max_retries: Maximum number of retry attempts (default: 3)
            initial_backoff: Initial backoff time in seconds (default: 1.0)

        Returns:
            Dict with test result tagged with repeat_num
        """
        # Add small delay before query to avoid overwhelming agent (rate limiting)
        # Random jitter prevents thundering herd when many workers start simultaneously
        query_delay = random.uniform(0.1, 0.5)  # 100-500ms jitter
        time.sleep(query_delay)

        last_exception = None

        for attempt in range(max_retries):
            try:
                # Use runner's run_single_test method
                result = self.runner.run_single_test(test_case, session_id=None)

                # Tag with repeat number
                result['repeat_num'] = repeat_num
                result['test_idx'] = test_idx

                return result

            except Exception as e:
                last_exception = e

                # Enhanced error categorization
                error_str = str(e).lower()
                is_agent_error = 'failed_precondition' in error_str or 'reasoning engine' in error_str
                is_rate_limit = any(keyword in error_str for keyword in ['rate limit', 'quota', '429', 'resource exhausted'])
                is_timeout = any(keyword in error_str for keyword in ['timeout', 'deadline', 'timed out'])
                is_connection = any(keyword in error_str for keyword in ['connection', 'unavailable', '503', '504', '500'])

                # Only retry specific error types (not agent execution errors)
                is_retryable = is_rate_limit or is_timeout or is_connection

                if not is_retryable or attempt == max_retries - 1:
                    # Log specific error category for debugging
                    if is_agent_error:
                        print(f"  ❌ Agent execution error (non-retryable): {type(e).__name__}")
                        logging.error(f"Agent execution error for question '{test_case.get('nl_question', 'unknown')}': {e}")
                    # Not retryable or final attempt - raise the error
                    raise

                # Calculate backoff with jitter (exponential backoff + randomization)
                backoff_time = initial_backoff * (2 ** attempt)
                jitter = random.uniform(0, backoff_time * 0.1)  # Add up to 10% jitter
                sleep_time = backoff_time + jitter

                print(f"  Retry {attempt + 1}/{max_retries} for '{test_case.get('nl_question', 'unknown')}' "
                      f"after {sleep_time:.1f}s (error: {type(e).__name__})")

                time.sleep(sleep_time)

        # Should not reach here, but raise last exception if we do
        raise last_exception

    def evaluate_with_repeats(
        self,
        golden_set_path: str,
        num_repeats: int = 3,
        max_retries: int = 2,
        initial_backoff: float = 2.0
    ) -> Tuple[List[Dict], Dict[str, Any], List[Dict]]:
        """
        Run evaluation multiple times IN PARALLEL and aggregate results.

        Args:
            golden_set_path: Path to golden set file
            num_repeats: Number of times to repeat each test (default: 3)
            max_retries: Maximum retry attempts per test (default: 2, reduced from 3)
            initial_backoff: Initial backoff time in seconds (default: 2.0, increased from 1.0)

        Returns:
            Tuple of:
                - all_results: List of ALL results (num_repeats * golden_set_size)
                - aggregated_metrics: Aggregated metrics with mean/std/min/max
                - failures: Failures from WORST run (for conservative improvement)
        """
        print(f"\n{'='*80}")
        print(f"RUNNING EVALUATION WITH {num_repeats} REPEATS (PARALLEL)")
        print(f"{'='*80}")
        print(f"Agent ID: {self.agent_id}")
        print(f"Golden Set: {golden_set_path}")
        print(f"Max Workers: {self.max_workers}\n")

        # Load test cases
        test_cases = self.loader.load(golden_set_path)

        # Create work items: (test_case, repeat_num, test_idx)
        work_items = []
        for repeat_num in range(1, num_repeats + 1):
            for idx, test_case in enumerate(test_cases):
                work_items.append((test_case, repeat_num, idx))

        total_tests = len(work_items)
        print(f"Total test executions: {total_tests} ({len(test_cases)} tests × {num_repeats} repeats)\n")

        # Execute tests in parallel
        all_results = []
        completed = 0

        print("Running tests in parallel...")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks with updated retry parameters
            future_to_work = {
                executor.submit(self._run_single_test, tc, rn, idx, max_retries, initial_backoff): (tc, rn, idx)
                for tc, rn, idx in work_items
            }

            # Collect results as they complete
            for future in as_completed(future_to_work):
                test_case, repeat_num, test_idx = future_to_work[future]
                try:
                    result = future.result()
                    with self._results_lock:
                        all_results.append(result)
                        completed += 1

                    # Progress indicator
                    if completed % 5 == 0 or completed == total_tests:
                        print(f"Progress: {completed}/{total_tests} tests completed ({completed*100//total_tests}%)")

                except Exception as e:
                    print(f"Error in test '{test_case.get('question', 'unknown')}': {e}")
                    # Add error result
                    with self._results_lock:
                        all_results.append({
                            "question_id": test_case.get("question_id"),
                            "question": test_case.get("nl_question"),
                            "error": str(e),
                            "repeat_num": repeat_num,
                            "test_idx": test_idx
                        })
                        completed += 1

        print(f"\n✓ All {total_tests} tests completed\n")

        # Group results by repeat_num for metrics calculation
        repeat_metrics = []
        for repeat_num in range(1, num_repeats + 1):
            repeat_results = [r for r in all_results if r.get('repeat_num') == repeat_num]

            # Sort by test_idx to maintain order
            repeat_results.sort(key=lambda r: r.get('test_idx', 0))

            # Save to file
            output_file = f"{self.output_path}.repeat{repeat_num}"
            self._save_results_to_file(repeat_results, output_file)

            # Calculate metrics
            metrics = self.runner.calculate_metrics(repeat_results)
            metrics['repeat_num'] = repeat_num
            repeat_metrics.append(metrics)

            print(f"Repeat {repeat_num} Accuracy: {metrics['accuracy']:.2f}%")

        # Aggregate metrics
        aggregated_metrics = self._aggregate_repeat_metrics(repeat_metrics)

        # Extract failures from WORST repeat (conservative approach)
        worst_repeat = min(repeat_metrics, key=lambda m: m['accuracy'])
        worst_repeat_results = [r for r in all_results if r['repeat_num'] == worst_repeat['repeat_num']]
        failures = self.runner.extract_failures(worst_repeat_results)

        # Display summary
        self._display_repeat_summary(aggregated_metrics, repeat_metrics, failures)

        return all_results, aggregated_metrics, failures

    def _save_results_to_file(self, results: List[Dict], output_path: str):
        """Save results to JSONL file."""
        import json
        with open(output_path, 'w') as f:
            for result in results:
                f.write(json.dumps(result) + "\n")

    def _aggregate_repeat_metrics(self, repeat_metrics: List[Dict]) -> Dict[str, Any]:
        """
        Aggregate metrics across repeats.

        Returns metrics with mean, std, min, max for accuracy and other stats.
        """
        import statistics

        accuracies = [m['accuracy'] for m in repeat_metrics]
        exact_matches = [m['exact_match'] for m in repeat_metrics]
        semantic_eqs = [m['semantically_equivalent'] for m in repeat_metrics]
        failures = [m['failures'] for m in repeat_metrics]

        return {
            'total': repeat_metrics[0]['total'],  # Same across all repeats
            'num_repeats': len(repeat_metrics),

            'accuracy': {
                'mean': round(statistics.mean(accuracies), 2),
                'std': round(statistics.stdev(accuracies), 2) if len(accuracies) > 1 else 0.0,
                'min': round(min(accuracies), 2),
                'max': round(max(accuracies), 2),
                'values': [round(a, 2) for a in accuracies]
            },

            'exact_match': {
                'mean': round(statistics.mean(exact_matches), 2),
                'std': round(statistics.stdev(exact_matches), 2) if len(exact_matches) > 1 else 0.0,
                'min': min(exact_matches),
                'max': max(exact_matches)
            },

            'semantically_equivalent': {
                'mean': round(statistics.mean(semantic_eqs), 2),
                'std': round(statistics.stdev(semantic_eqs), 2) if len(semantic_eqs) > 1 else 0.0,
                'min': min(semantic_eqs),
                'max': max(semantic_eqs)
            },

            'failures': {
                'mean': round(statistics.mean(failures), 2),
                'std': round(statistics.stdev(failures), 2) if len(failures) > 1 else 0.0,
                'min': min(failures),
                'max': max(failures)
            },

            'error_count': repeat_metrics[0].get('error_count', 0)  # Assuming same across repeats
        }

    def _display_repeat_summary(
        self,
        aggregated_metrics: Dict[str, Any],
        repeat_metrics: List[Dict],
        failures: List[Dict]
    ):
        """Display aggregated evaluation summary."""
        print(f"\n{'='*80}")
        print(f"AGGREGATED RESULTS ({aggregated_metrics['num_repeats']} repeats)")
        print(f"{'='*80}\n")

        acc = aggregated_metrics['accuracy']
        print(f"Accuracy: {acc['mean']:.2f}% ± {acc['std']:.2f}%")
        print(f"  Range: {acc['min']:.2f}% - {acc['max']:.2f}%")
        print(f"  Individual runs: {acc['values']}")

        print(f"\nBreakdown:")
        exact = aggregated_metrics['exact_match']
        print(f"  Exact Match: {exact['mean']:.1f} ± {exact['std']:.1f} (range: {exact['min']}-{exact['max']})")

        semantic = aggregated_metrics['semantically_equivalent']
        print(f"  Semantically Equivalent: {semantic['mean']:.1f} ± {semantic['std']:.1f} (range: {semantic['min']}-{semantic['max']})")

        fails = aggregated_metrics['failures']
        print(f"  Failures: {fails['mean']:.1f} ± {fails['std']:.1f} (range: {fails['min']}-{fails['max']})")

        if failures:
            print(f"\n{'='*80}")
            print(f"FAILURES FROM WORST RUN ({len(failures)} failures)")
            print(f"{'='*80}")
            for i, failure in enumerate(failures[:5], 1):  # Show first 5
                print(f"\n{i}. {failure['question']}")
                print(f"   Issue: {failure['issue']}")
            if len(failures) > 5:
                print(f"\n... and {len(failures) - 5} more failures")

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
