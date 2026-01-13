"""Report generator for iterative agent optimization.

Generates comprehensive markdown reports with:
- Executive summary with key results
- ASCII charts and embedded visualizations
- Iteration-by-iteration details
- Configuration evolution tracking
- Final recommendations
- Reproduction commands
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from statistics import mean, stdev


class OptimizationReportGenerator:
    """Generates comprehensive markdown reports for optimization runs."""

    def __init__(self, output_dir: str = "results"):
        """Initialize report generator.

        Args:
            output_dir: Directory to write reports to
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def generate_report(
        self,
        trajectory_history: Dict,
        chart_paths: List[str],
        agent_id: str,
        iteration_count: Optional[int] = None,
        run_id: Optional[str] = None,
    ) -> str:
        """Generate comprehensive optimization report.

        Args:
            trajectory_history: Optimization trajectory data with metrics and configs
            chart_paths: List of paths to generated chart images
            agent_id: ID of the agent being optimized
            iteration_count: Number of iterations (inferred if not provided)
            run_id: Run timestamp ID (extracted from trajectory if not provided)

        Returns:
            Path to generated report file
        """
        # Infer iteration count from trajectory
        if iteration_count is None:
            iteration_count = len(trajectory_history.get("iterations", []))

        # Extract run_id from trajectory history start_time if not provided
        if run_id is None:
            start_time = trajectory_history.get("start_time", "")
            if start_time:
                # Parse ISO format timestamp and convert to run_id format
                try:
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    run_id = dt.strftime("%Y%m%d_%H%M%S")
                except:
                    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            else:
                run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Build report sections
        sections = [
            self._generate_header(agent_id, iteration_count, run_id),
            self._generate_executive_summary(trajectory_history),
            self._generate_visualizations(chart_paths),
            self._generate_iteration_details(trajectory_history),
            self._generate_configuration_evolution(trajectory_history),
            self._generate_recommendations(trajectory_history),
            self._generate_appendix(trajectory_history, agent_id),
        ]

        # Combine all sections
        report_content = "\n\n".join(sections)

        # Write to file using consistent run_id
        report_path = self.output_dir / f"OPTIMIZATION_REPORT_{run_id}.md"
        report_path.write_text(report_content)

        # Generate assist token registry
        self._generate_assist_token_registry(trajectory_history, agent_id, run_id)

        return str(report_path)

    def _generate_header(self, agent_id: str, iteration_count: int, run_id: str) -> str:
        """Generate report header."""
        import os
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get judgement model from environment
        judgement_model = os.getenv("JUDGEMENT_MODEL", "gemini-2.5-pro")

        return f"""# Agent Optimization Report

**Run ID:** `{run_id}`
**Agent ID:** `{agent_id}`
**Report Generated:** {timestamp}
**Total Iterations:** {iteration_count}
**Framework:** Data Insights Agent (DIA) Test Harness
**Judgement Model:** {judgement_model}

## Report Features

This comprehensive optimization report includes:
- ✅ **Metrics & Charts**: Accuracy trends, metric breakdowns, and performance analysis
- ✅ **Configuration Links**: Direct links to all deployed agent configurations
- ✅ **Execution Logs**: References to log files and Cloud Console links
- ✅ **Expandable Question-Level Performance**: Click each failure to see detailed SQL comparisons and AI judgement analysis
- ✅ **AI Model Attribution**: All AI models used for judgements and improvements are documented
- ✅ **Iteration Feedback**: Detailed reasoning for why each configuration change was made

---
"""

    def _normalize_iteration(self, iteration: Dict) -> Dict:
        """Normalize iteration to new format (backward compatibility).

        Converts old format with "metrics", "config", "failures"
        to new format with "evaluation" and "configuration".
        """
        # If already in new format, return as-is
        if "evaluation" in iteration:
            return iteration

        # Convert old format to new format
        normalized = iteration.copy()

        # Convert "config" -> "configuration"
        if "config" in normalized and "configuration" not in normalized:
            normalized["configuration"] = normalized["config"]

        # Convert "metrics" + "failures" -> "evaluation"
        if "metrics" in normalized and "evaluation" not in normalized:
            metrics = normalized["metrics"]
            failures = normalized.get("failures", [])

            # Extract accuracy (handle both dict and float formats)
            if isinstance(metrics.get("accuracy"), dict):
                accuracy = metrics["accuracy"].get("mean", 0.0) / 100.0
                repeat_measurements = [v / 100.0 for v in metrics["accuracy"].get("values", [])]
            else:
                accuracy = metrics.get("accuracy", 0.0)
                if accuracy > 1.0:  # Convert percentage to decimal
                    accuracy = accuracy / 100.0
                repeat_measurements = []

            total_cases = metrics.get("total", 0)
            correct = int(accuracy * total_cases) if total_cases > 0 else 0

            # Build evaluation structure
            train_eval = {
                "accuracy": accuracy,
                "total_cases": total_cases,
                "correct": correct,
                "failures": failures
            }

            if repeat_measurements and len(repeat_measurements) > 1:
                train_eval["repeat_measurements"] = repeat_measurements

            normalized["evaluation"] = {"train": train_eval}

            # Add test evaluation if available
            if "test_metrics" in normalized:
                test_metrics = normalized["test_metrics"]
                test_failures = normalized.get("test_failures", [])

                if isinstance(test_metrics.get("accuracy"), dict):
                    test_accuracy = test_metrics["accuracy"].get("mean", 0.0) / 100.0
                    test_repeat = [v / 100.0 for v in test_metrics["accuracy"].get("values", [])]
                else:
                    test_accuracy = test_metrics.get("accuracy", 0.0)
                    if test_accuracy > 1.0:
                        test_accuracy = test_accuracy / 100.0
                    test_repeat = []

                test_total = test_metrics.get("total", 0)
                test_correct = int(test_accuracy * test_total) if test_total > 0 else 0

                test_eval = {
                    "accuracy": test_accuracy,
                    "total_cases": test_total,
                    "correct": test_correct,
                    "failures": test_failures
                }

                if test_repeat and len(test_repeat) > 1:
                    test_eval["repeat_measurements"] = test_repeat

                normalized["evaluation"]["test"] = test_eval

        return normalized

    def _generate_executive_summary(self, trajectory: Dict) -> str:
        """Generate executive summary with key results including flexible scoring."""
        iterations = trajectory.get("iterations", [])
        if not iterations:
            return "## Executive Summary\n\nNo iterations completed."

        # Extract metrics across iterations
        train_accuracies = []
        test_accuracies = []
        train_avg_scores = []

        for iteration in iterations:
            # Normalize to new format
            iteration = self._normalize_iteration(iteration)

            evals = iteration.get("evaluation", {})
            if "train" in evals:
                train_accuracies.append(evals["train"].get("accuracy", 0.0))

                # Calculate average score from results
                results = iteration.get("results", [])
                if results:
                    scores = [r.get("score_details", {}).get("total_score", 0) for r in results]
                    avg_score = sum(scores) / len(scores) if scores else 0
                    train_avg_scores.append(avg_score)
                else:
                    train_avg_scores.append(0)

            if "test" in evals:
                test_accuracies.append(evals["test"].get("accuracy", 0.0))

        # Calculate improvement
        initial_train = train_accuracies[0] if train_accuracies else 0.0
        final_train = train_accuracies[-1] if train_accuracies else 0.0
        train_improvement = final_train - initial_train

        initial_score = train_avg_scores[0] if train_avg_scores else 0.0
        final_score = train_avg_scores[-1] if train_avg_scores else 0.0
        score_improvement = final_score - initial_score

        initial_test = test_accuracies[0] if test_accuracies else 0.0
        final_test = test_accuracies[-1] if test_accuracies else 0.0
        test_improvement = final_test - initial_test

        # Build summary table
        summary = f"""## Executive Summary

### Flexible Scoring Enabled

This optimization used **100-point flexible scoring** that recognizes partial correctness:
- Queries are scored across 6 categories (Data Source, Filtering, Columns, Grouping, Ordering, Format)
- Pass threshold: 80/100 points
- Provides more nuanced feedback than binary pass/fail

### Key Results

| Metric | Initial | Final | Improvement |
|--------|---------|-------|-------------|
| **Avg Score (Flexible)** | {initial_score:.1f}/100 | {final_score:.1f}/100 | {score_improvement:+.1f} |
| **Pass Rate (≥80pts)** | {initial_train:.1%} | {final_train:.1%} | {train_improvement:+.1%} |
"""

        if test_accuracies:
            summary += f"| **Test Pass Rate** | {initial_test:.1%} | {final_test:.1%} | {test_improvement:+.1%} |\n"

        summary += f"| **Iterations** | - | {len(iterations)} | - |\n"

        # Add ASCII chart of progress (using avg scores)
        summary += "\n### Progress Chart (Avg Score)\n\n```\n"
        if train_avg_scores:
            # Normalize scores to 0-1 range for chart
            normalized_scores = [s / 100.0 for s in train_avg_scores]
            summary += self._generate_ascii_chart(normalized_scores, "Average Score")
        else:
            summary += self._generate_ascii_chart(train_accuracies, "Pass Rate")
        summary += "```\n"

        return summary

    def _generate_ascii_chart(
        self, values: List[float], title: str, width: int = 60, height: int = 10
    ) -> str:
        """Generate ASCII line chart."""
        if not values:
            return f"{title}: No data\n"

        min_val = min(values)
        max_val = max(values)
        range_val = max_val - min_val if max_val > min_val else 1.0

        chart = f"{title}\n"
        chart += f"Max: {max_val:.2%}  Min: {min_val:.2%}\n\n"

        # Generate chart rows (top to bottom)
        for row in range(height):
            threshold = max_val - (row / height) * range_val
            line = ""

            for i, val in enumerate(values):
                if val >= threshold:
                    line += "█"
                else:
                    line += " "

            # Add Y-axis label
            chart += f"{threshold:6.1%} |{line}\n"

        # Add X-axis
        chart += "       +" + "-" * len(values) + "\n"
        chart += "        " + "".join(str(i % 10) for i in range(len(values))) + "\n"
        chart += "        Iteration\n"

        return chart

    def _generate_visualizations(self, chart_paths: List[str]) -> str:
        """Generate visualizations section with embedded images."""
        if not chart_paths:
            return "## Visualizations\n\nNo charts generated."

        section = "## Visualizations\n\n"

        for chart_path in chart_paths:
            path = Path(chart_path)
            if not path.exists():
                continue

            # Use relative path from the report location (within the same run directory)
            # Extract just the filename and prepend 'charts/' directory
            path_str = str(path)
            if 'charts/' in path_str:
                # Extract just the filename from the charts directory
                filename = path.name
                rel_path = f"charts/{filename}"
            else:
                rel_path = path.name

            # Infer chart title from filename
            title = path.stem.replace("_", " ").title()

            section += f"### {title}\n\n"
            section += f"![{title}]({rel_path})\n\n"

        return section

    def _generate_iteration_details(self, trajectory: Dict) -> str:
        """Generate detailed iteration-by-iteration breakdown."""
        iterations = trajectory.get("iterations", [])
        if not iterations:
            return "## Iteration Details\n\nNo iterations completed."

        section = "## Iteration Details\n\n"

        for idx, iteration in enumerate(iterations):
            # Normalize to new format
            iteration = self._normalize_iteration(iteration)

            section += f"### Iteration {idx}\n\n"

            # Metrics
            evals = iteration.get("evaluation", {})
            if "train" in evals:
                train_acc = evals["train"].get("accuracy", 0.0)
                train_total = evals["train"].get("total_cases", 0)
                train_correct = evals["train"].get("correct", 0)

                section += f"**Train Metrics:**\n"
                section += f"- Accuracy: {train_acc:.2%} ({train_correct}/{train_total})\n"

                # Show repeat measurements if available
                if "repeat_measurements" in evals["train"]:
                    repeats = evals["train"]["repeat_measurements"]
                    if len(repeats) > 1:
                        repeat_mean = mean(repeats)
                        repeat_std = stdev(repeats)
                        section += f"- Repeat measurements: {repeat_mean:.2%} ± {repeat_std:.2%}\n"

            if "test" in evals:
                test_acc = evals["test"].get("accuracy", 0.0)
                test_total = evals["test"].get("total_cases", 0)
                test_correct = evals["test"].get("correct", 0)

                section += f"\n**Test Metrics:**\n"
                section += f"- Accuracy: {test_acc:.2%} ({test_correct}/{test_total})\n"

            # Add color-coded results table before failures
            section += self._format_results_table(iteration, evals.get("train", {}))

            # Failures (truncated)
            section += self._format_failures(evals.get("train", {}))

            # Configuration details - show ALL fields
            config = iteration.get("configuration", iteration.get("config", {}))  # Backward compatible
            section += f"\n**Configuration Fields:**\n"

            if "nl2sql_prompt" in config:
                prompt_preview = config["nl2sql_prompt"][:200].replace("\n", " ")
                section += f"- **nl2sql_prompt**: `{prompt_preview}...` ({len(config['nl2sql_prompt'])} chars)\n"

            if "schema_description" in config and config["schema_description"]:
                schema_preview = str(config["schema_description"])[:150].replace("\n", " ")
                section += f"- **schema_description**: `{schema_preview}...` ({len(str(config['schema_description']))} chars)\n"

            if "nl2sql_examples" in config and config["nl2sql_examples"]:
                num_examples = len(config["nl2sql_examples"])
                section += f"- **nl2sql_examples**: {num_examples} examples provided\n"

            if "nl2py_prompt" in config and config["nl2py_prompt"]:
                section += f"- **nl2py_prompt**: Set ({len(str(config['nl2py_prompt']))} chars)\n"

            if "allowed_tables" in config and config["allowed_tables"]:
                section += f"- **allowed_tables**: {len(config['allowed_tables'])} tables whitelisted\n"

            if "blocked_tables" in config and config["blocked_tables"]:
                section += f"- **blocked_tables**: {len(config['blocked_tables'])} tables blocked\n"

            # Prompt changes description with AI model information
            if iteration.get("prompt_changes"):
                section += f"\n**Changes Made:** {iteration['prompt_changes']}\n"

            # Add AI model information if available
            import os
            judgement_model = os.getenv("JUDGEMENT_MODEL", "gemini-2.5-pro")
            improvement_model = os.getenv("PROMPT_IMPROVEMENT_MODEL", "gemini-3-pro-preview")
            config_model = os.getenv("CONFIG_ANALYSIS_MODEL", "gemini-3-pro-preview")

            section += f"\n**AI Models Used:**\n"
            section += f"- **SQL Judgement**: {judgement_model} (for semantic SQL equivalence evaluation)\n"
            section += f"- **Prompt Improvement**: {improvement_model} (for analyzing failures and suggesting improvements)\n"
            section += f"- **Config Analysis**: {config_model} (for recommending configuration changes)\n"

            # Show overall iteration feedback (AI reasoning for changes)
            if iteration.get("prompt_changes") and idx > 0:
                section += f"\n<details>\n"
                section += f"<summary><b>📋 View AI Improvement Reasoning</b></summary>\n\n"
                section += f"**Why these changes were made:**\n\n"
                section += f"{iteration['prompt_changes']}\n\n"

                # Show comparison with previous iteration
                prev_iteration = iterations[idx-1] if idx > 0 else None
                if prev_iteration:
                    prev_acc = self._normalize_iteration(prev_iteration).get("evaluation", {}).get("train", {}).get("accuracy", 0.0)
                    curr_acc = evals.get("train", {}).get("accuracy", 0.0)
                    improvement = curr_acc - prev_acc
                    section += f"**Performance Change:** {improvement:+.2%} (from {prev_acc:.2%} to {curr_acc:.2%})\n\n"

                section += f"</details>\n\n"

            section += "\n---\n\n"

        return section

    def _format_results_table(self, iteration: Dict, eval_data: Dict) -> str:
        """Format color-coded results table with flexible scoring rubric.

        Args:
            iteration: Iteration data containing all test results
            eval_data: Evaluation data with failures and successes

        Returns:
            Markdown table with color-coded results and rubric scores
        """
        # Get all results from the iteration (including successes and failures)
        all_results = iteration.get("results", [])
        if not all_results:
            # Fallback: try to reconstruct from failures
            all_results = eval_data.get("failures", [])

        if not all_results:
            return "\n**Results Table:** No test results available\n\n"

        section = "\n### Flexible Scoring Rubric\n\n"
        section += "**100-Point Scoring System:**\n"
        section += "- 🟢 **95-100**: Excellent (near perfect)\n"
        section += "- 🟡 **80-94**: Good (passes threshold)\n"
        section += "- 🟠 **60-79**: Partial (some issues)\n"
        section += "- 🔴 **0-59**: Failed (major issues)\n\n"

        section += "**Rubric Categories:**\n"
        section += "| Category | Points | Description |\n"
        section += "|----------|--------|-------------|\n"
        section += "| Data Source | 20 | Correct tables and joins |\n"
        section += "| Filtering | 25 | Accurate WHERE clauses |\n"
        section += "| Columns | 20 | Correct SELECT fields |\n"
        section += "| Grouping | 15 | Proper GROUP BY and aggregation |\n"
        section += "| Ordering | 10 | Correct ORDER BY and LIMIT |\n"
        section += "| Format | 10 | Query structure and syntax |\n\n"

        # Group results by question (aggregate across repeats)
        questions_map = {}
        for result in all_results:
            question_id = result.get("question_id") or result.get("question", "Unknown")
            question = result.get("question", "Unknown")
            repeat_num = result.get("repeat_num", 1)

            if question_id not in questions_map:
                questions_map[question_id] = {
                    "question": question,
                    "repeats": []
                }
            questions_map[question_id]["repeats"].append({
                "repeat_num": repeat_num,
                "score": result.get("score_details", {}).get("total_score", 0),
                "score_details": result.get("score_details", {}),
                "result": result
            })

        section += "### Question-Level Results (Aggregated Across Repeats)\n\n"
        section += "| # | Question | Avg Score | Status | Repeats | Breakdown |\n"
        section += "|---|----------|-----------|--------|---------|------------|\n"

        for i, (question_id, qdata) in enumerate(sorted(questions_map.items()), 1):
            question = qdata["question"][:50]  # Truncate long questions
            repeats = qdata["repeats"]

            # Calculate average score across repeats
            scores = [r["score"] for r in repeats]
            avg_score = sum(scores) / len(scores) if scores else 0

            # Determine color and status based on average score
            if avg_score >= 95:
                status_icon = "🟢"
                status_text = "Excellent"
            elif avg_score >= 80:
                status_icon = "🟡"
                status_text = "Pass"
            elif avg_score >= 60:
                status_icon = "🟠"
                status_text = "Partial"
            else:
                status_icon = "🔴"
                status_text = "Fail"

            # Show individual repeat scores
            repeat_scores_str = ", ".join([f"R{r['repeat_num']}:{r['score']}" for r in sorted(repeats, key=lambda x: x["repeat_num"])])

            # Build breakdown string using first repeat (they should be similar)
            category_scores = repeats[0]["score_details"].get("category_scores", {})
            if category_scores:
                d = category_scores.get('data_source', 0)
                f = category_scores.get('filtering', 0)
                c = category_scores.get('columns', 0)
                g = category_scores.get('grouping', 0)
                o = category_scores.get('ordering', 0)
                fmt = category_scores.get('format', 0)
                breakdown = f"D:{d}/20 F:{f}/25 C:{c}/20 G:{g}/15 O:{o}/10 Fmt:{fmt}/10"
            else:
                # Fallback for old format
                is_match = repeats[0]["result"].get("is_match", False)
                breakdown = "Exact" if is_match else "Different"

            section += f"| {i} | {question}... | **{avg_score:.1f}**/100 | {status_icon} {status_text} | {repeat_scores_str} | {breakdown} |\n"

        # Calculate summary statistics
        total = len(all_results)
        scores = [r.get("score_details", {}).get("total_score", 0) for r in all_results]
        avg_score = sum(scores) / len(scores) if scores else 0
        excellent = sum(1 for s in scores if s >= 95)
        good = sum(1 for s in scores if 80 <= s < 95)
        partial = sum(1 for s in scores if 60 <= s < 80)
        failed = sum(1 for s in scores if s < 60)

        section += f"\n**Summary:** {total} tests | Avg: **{avg_score:.1f}/100** | "
        section += f"🟢 {excellent} excellent | "
        section += f"🟡 {good} good | "
        section += f"🟠 {partial} partial | "
        section += f"🔴 {failed} failed\n\n"

        section += f"**Breakdown Legend:** D=Data Source (/20), F=Filtering (/25), C=Columns (/20), G=Grouping (/15), O=Ordering (/10), Fmt=Format (/10)\n\n"

        return section

    def _format_failures(self, eval_data: Dict, max_failures: int = 5, expandable: bool = True) -> str:
        """Format failure list with optional expandable details.

        Args:
            eval_data: Evaluation data containing failures
            max_failures: Number of failures to show in summary (if not expandable)
            expandable: If True, use HTML details/summary for expandable sections
        """
        failures = eval_data.get("failures", [])
        if not failures:
            return "\n**Failures:** None\n"

        section = f"\n**Failures:** {len(failures)} total\n\n"

        if expandable:
            # Use HTML details/summary tags for expandable question-level performance
            for i, failure in enumerate(failures):
                question = failure.get("question", "Unknown")
                error = failure.get("issue", "Unknown error")
                explanation = failure.get("explanation", "")
                expected_sql = failure.get("expected_sql", "")
                generated_sql = failure.get("generated_sql", "")
                score_details = failure.get("score_details", {})
                total_score = score_details.get("total_score", 0)

                # Determine color based on score
                if total_score >= 80:
                    score_icon = "🟡"
                elif total_score >= 60:
                    score_icon = "🟠"
                else:
                    score_icon = "🔴"

                # Create expandable section with score
                section += f"<details>\n"
                section += f"<summary><b>{i+1}. {question}</b> - {score_icon} <b>{total_score}/100</b> - <i>{error[:60]}...</i></summary>\n\n"

                # Show rubric breakdown if available
                if score_details and score_details.get("category_scores"):
                    section += f"**Rubric Breakdown:**\n"
                    category_scores = score_details["category_scores"]
                    section += f"| Category | Score | Max |\n"
                    section += f"|----------|-------|-----|\n"
                    section += f"| Data Source | {category_scores.get('data_source', 0)} | 20 |\n"
                    section += f"| Filtering | {category_scores.get('filtering', 0)} | 25 |\n"
                    section += f"| Columns | {category_scores.get('columns', 0)} | 20 |\n"
                    section += f"| Grouping | {category_scores.get('grouping', 0)} | 15 |\n"
                    section += f"| Ordering | {category_scores.get('ordering', 0)} | 10 |\n"
                    section += f"| Format | {category_scores.get('format', 0)} | 10 |\n"
                    section += f"| **TOTAL** | **{total_score}** | **100** |\n\n"

                section += f"**Issue:** {error}\n\n"

                if expected_sql:
                    section += f"**Expected SQL:**\n```sql\n{expected_sql}\n```\n\n"

                if generated_sql:
                    section += f"**Generated SQL:**\n```sql\n{generated_sql}\n```\n\n"

                if explanation:
                    # Show full explanation without truncation
                    section += f"**AI Judgement Analysis:**\n{explanation}\n\n"

                section += f"</details>\n\n"
        else:
            # Traditional truncated format
            for i, failure in enumerate(failures[:max_failures]):
                question = failure.get("question", "Unknown")
                error = failure.get("issue", "Unknown error")

                section += f"{i+1}. **Q:** {question}\n"
                section += f"   **Error:** {error[:150]}\n"

            if len(failures) > max_failures:
                section += f"\n... and {len(failures) - max_failures} more failures (see appendix)\n"

        return section

    def _generate_configuration_evolution(self, trajectory: Dict) -> str:
        """Generate configuration evolution table showing all config fields."""
        iterations = trajectory.get("iterations", [])
        if not iterations:
            return "## Configuration Evolution\n\nNo configurations tracked."

        section = "## Configuration Evolution\n\n"
        section += "Summary of configuration changes and performance across iterations.\n\n"

        # Performance-focused table with flexible scoring metrics
        section += "| Iter | Avg Score | Pass Rate | Exact | Semantic | Examples | Prompt Changed | Schema Changed |\n"
        section += "|------|-----------|-----------|-------|----------|----------|----------------|----------------|\n"

        prev_prompt = None
        prev_schema = None

        for idx, iteration in enumerate(iterations):
            # Normalize to new format
            iteration = self._normalize_iteration(iteration)

            evals = iteration.get("evaluation", {})
            config = iteration.get("configuration", iteration.get("config", {}))  # Backward compatible

            # Get flexible scoring metrics (with backward compatibility)
            train_eval = evals.get("train", {})

            # Try to get flexible scoring metrics, fallback to old format
            avg_score = train_eval.get("avg_score")
            pass_rate = train_eval.get("pass_rate")

            # If not available, calculate from accuracy (old format)
            if avg_score is None and "accuracy" in train_eval:
                # Old format: accuracy is 0-1, convert to percentage for display
                accuracy = train_eval.get("accuracy", 0.0) * 100
                avg_score = accuracy  # Use accuracy as score proxy
                pass_rate = accuracy  # Use accuracy as pass rate proxy
            else:
                avg_score = avg_score or 0.0
                pass_rate = pass_rate or 0.0

            exact_match = train_eval.get("exact_match", 0)
            semantic = train_eval.get("semantically_equivalent", 0)

            # Config details
            num_examples = len(config.get("nl2sql_examples", []))
            current_prompt = config.get("nl2sql_prompt", "")
            current_schema = config.get("schema_description", "")

            # Detect changes
            prompt_changed = "✓" if idx == 0 else ("✓ Yes" if current_prompt != prev_prompt else "—")
            schema_changed = "✓" if idx == 0 else ("✓ Yes" if current_schema != prev_schema else "—")

            section += (
                f"| {idx} | {avg_score:.1f}/100 | {pass_rate:.1f}% | "
                f"{exact_match} | {semantic} | {num_examples} | "
                f"{prompt_changed} | {schema_changed} |\n"
            )

            prev_prompt = current_prompt
            prev_schema = current_schema

        # Add expanded details section
        section += "\n### Configuration Details by Iteration\n\n"

        for idx, iteration in enumerate(iterations):
            iteration = self._normalize_iteration(iteration)
            config = iteration.get("configuration", iteration.get("config", {}))

            section += f"**Iteration {idx}:**\n"

            # Count characters for size reference
            prompt_len = len(config.get("nl2sql_prompt", ""))
            schema_len = len(str(config.get("schema_description", ""))) if config.get("schema_description") else 0
            num_examples = len(config.get("nl2sql_examples", []))

            section += f"- Prompt: {prompt_len:,} characters\n"
            section += f"- Schema: {schema_len:,} characters\n"
            section += f"- Examples: {num_examples} SQL examples\n"

            # Table access
            allowed = len(config.get("allowed_tables", []))
            blocked = len(config.get("blocked_tables", []))
            if allowed or blocked:
                section += f"- Table Access: {allowed} allowed, {blocked} blocked\n"
            else:
                section += f"- Table Access: All tables\n"

            # Python prompt
            if config.get("nl2py_prompt"):
                py_len = len(config.get("nl2py_prompt", ""))
                section += f"- Python Prompt: Set ({py_len:,} characters)\n"

            section += "\n"

        return section

    def _generate_recommendations(self, trajectory: Dict) -> str:
        """Generate actionable recommendations based on results."""
        iterations = trajectory.get("iterations", [])
        if not iterations:
            return "## Recommendations\n\nInsufficient data for recommendations."

        section = "## Recommendations\n\n"

        # Get final iteration metrics
        final = self._normalize_iteration(iterations[-1])
        final_train = final.get("evaluation", {}).get("train", {}).get("accuracy", 0.0)
        final_test = final.get("evaluation", {}).get("test", {}).get("accuracy", 0.0)

        # Analyze performance
        if final_train >= 0.9:
            section += "### ✅ Strong Performance\n\n"
            section += f"The agent achieved {final_train:.2%} training accuracy. "
            section += "Consider deploying this configuration to production.\n\n"
        elif final_train >= 0.7:
            section += "### ⚠️ Moderate Performance\n\n"
            section += f"The agent achieved {final_train:.2%} training accuracy. "
            section += "Consider additional iterations or manual prompt refinement.\n\n"
        else:
            section += "### ❌ Poor Performance\n\n"
            section += f"The agent achieved only {final_train:.2%} training accuracy. "
            section += "Significant prompt engineering or architectural changes needed.\n\n"

        # Check for overfitting
        if final_test > 0 and (final_train - final_test) > 0.15:
            section += "### 🔍 Overfitting Detected\n\n"
            section += f"Training accuracy ({final_train:.2%}) significantly exceeds "
            section += f"test accuracy ({final_test:.2%}). Consider:\n"
            section += "- Reducing prompt complexity\n"
            section += "- Using more diverse training examples\n"
            section += "- Adding regularization techniques\n\n"

        # Check for improvement trend
        train_accs = [
            self._normalize_iteration(it).get("evaluation", {}).get("train", {}).get("accuracy", 0.0)
            for it in iterations
        ]
        if len(train_accs) >= 2:
            recent_improvement = train_accs[-1] - train_accs[-2]
            if recent_improvement > 0.05:
                section += "### 📈 Strong Improvement Trend\n\n"
                section += f"Recent iteration showed +{recent_improvement:.2%} improvement. "
                section += "Continue optimization with current strategy.\n\n"
            elif abs(recent_improvement) < 0.01:
                section += "### 📊 Plateau Detected\n\n"
                section += "Minimal improvement in recent iterations. Consider:\n"
                section += "- Trying different optimization strategies\n"
                section += "- Adjusting learning parameters\n"
                section += "- Manual inspection of failure cases\n\n"

        # Failure analysis
        final_failures = final.get("evaluation", {}).get("train", {}).get("failures", [])
        if final_failures:
            section += f"### 🔧 Address {len(final_failures)} Remaining Failures\n\n"
            section += "Top failure categories to investigate:\n"

            # Group failures by error type (simple heuristic)
            error_types = {}
            for failure in final_failures[:10]:
                error = failure.get("error", "Unknown")
                error_type = error[:50]  # First 50 chars as category
                error_types[error_type] = error_types.get(error_type, 0) + 1

            for error_type, count in sorted(
                error_types.items(), key=lambda x: x[1], reverse=True
            ):
                section += f"- {count}x: `{error_type}...`\n"

            section += "\n"

        return section

    def _generate_appendix(self, trajectory: Dict, agent_id: str) -> str:
        """Generate appendix with raw data and reproduction commands."""
        section = "## Appendix\n\n"

        # Extract timestamp from trajectory start_time
        start_time = trajectory.get("start_time", "")
        timestamp = ""
        if start_time:
            # Parse timestamp from ISO format: 2026-01-09T22:51:26.984219
            # Extract YYYYMMDD_HHMMSS format
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(start_time)
                timestamp = dt.strftime("%Y%m%d_%H%M%S")
            except:
                pass

        # Raw data reference
        section += "### Generated Artifacts\n\n"
        section += "**Trajectory and Metrics:**\n"
        if timestamp:
            section += f"- [`trajectory_history_{timestamp}.json`](trajectory_history_{timestamp}.json) - Complete optimization trajectory with all iterations\n"
            section += f"- [`eval_train_{timestamp}.jsonl.repeat1`](eval_train_{timestamp}.jsonl.repeat1) - Training evaluation (repeat 1)\n"
            section += f"- [`eval_train_{timestamp}.jsonl.repeat2`](eval_train_{timestamp}.jsonl.repeat2) - Training evaluation (repeat 2)\n"
            section += f"- [`eval_train_{timestamp}.jsonl.repeat3`](eval_train_{timestamp}.jsonl.repeat3) - Training evaluation (repeat 3)\n"
            section += f"- [`ASSIST_TOKEN_REGISTRY.md`](ASSIST_TOKEN_REGISTRY.md) - Debugging tokens for all queries with error categorization\n\n"
        else:
            section += f"- `trajectory_history_{agent_id}.json` - Complete optimization trajectory\n"
            section += "- `eval_train_*.jsonl.repeat*` - Evaluation results\n"
            section += "- `ASSIST_TOKEN_REGISTRY.md` - Assist tokens for debugging\n\n"

        # Add log file links
        # Get project ID from environment or trajectory
        import os
        project_id = trajectory.get('project_id') or os.getenv('GOOGLE_CLOUD_PROJECT', 'your-project-id')

        section += "**Execution Logs:**\n"
        section += "- Optimization execution logs available in terminal output or log files\n"
        section += f"- [View agent in Cloud Console](https://console.cloud.google.com/gen-app-builder/agents?project={project_id})\n"
        section += f"- [View BigQuery dataset](https://console.cloud.google.com/bigquery?project={project_id})\n\n"

        # Config snapshots
        iterations = trajectory.get("iterations", [])
        if iterations and timestamp:
            section += "**Configuration Snapshots:**\n"
            for idx, iteration in enumerate(iterations):
                iter_num = iteration.get("iteration", idx + 1)
                section += f"- Iteration {iter_num}:\n"
                section += f"  - [`config_iteration_{iter_num}_suggested_{timestamp}.json`](configs/config_iteration_{iter_num}_suggested_{timestamp}.json) - AI-suggested configuration\n"
                section += f"  - [`config_iteration_{iter_num}_final_{timestamp}.json`](configs/config_iteration_{iter_num}_final_{timestamp}.json) - Deployed configuration\n"
            section += "\n"

        # Charts
        section += "**Visualizations:**\n"
        section += "- [`charts/multi_metric_comparison.png`](charts/multi_metric_comparison.png) - **Multi-metric comparison** (exact match, semantic similarity, pass rate)\n"
        section += "- [`charts/average_score_over_time.png`](charts/average_score_over_time.png) - **Average flexible scores** over iterations\n"
        section += "- [`charts/rubric_category_breakdown.png`](charts/rubric_category_breakdown.png) - **Rubric category breakdown** by iteration\n"
        section += "- [`charts/metric_breakdown.png`](charts/metric_breakdown.png) - **Query results breakdown** (exact/semantic/partial/failed)\n"
        section += "- [`charts/score_distribution_histogram.png`](charts/score_distribution_histogram.png) - **Score distribution** histogram\n"
        section += "- [`charts/accuracy_over_time.png`](charts/accuracy_over_time.png) - Accuracy progression\n"
        section += "- [`charts/improvement_deltas.png`](charts/improvement_deltas.png) - Iteration-to-iteration changes\n"
        section += "- [`charts/question_heatmap.png`](charts/question_heatmap.png) - Per-question performance (if available)\n\n"

        # Reproduction commands
        section += "### Reproduction Commands\n\n"
        section += "To reproduce this optimization run:\n\n"

        # Extract config name from trajectory
        agent_name = trajectory.get("agent_name", "unknown")
        config_file = "configs/mcd_config.json"  # Default
        if "aggressive" in agent_name.lower():
            config_file = "configs/mcd_config_aggressive.json"
        elif "baseline" in agent_name.lower():
            config_file = "configs/baseline_config.json"

        # Get iteration count from trajectory
        max_iterations = len(iterations) if iterations else 10

        section += "```bash\n"
        section += "# 1. Set up environment\n"
        section += "source .venv/bin/activate\n"
        section += "export GOOGLE_CLOUD_PROJECT=your-project-id\n"
        section += "export DIA_LOCATION=global\n"
        section += "export DIA_ENGINE_ID=your-engine-id\n"
        section += "export BQ_DATASET_ID=your-dataset-id\n\n"

        section += "# 2. Deploy agent (one-time - if not already deployed)\n"
        section += f"dia-harness deploy --config-file {config_file}\n\n"

        section += "# 3. Authorize agent via Gemini Enterprise UI (one-time)\n"
        section += "#    Visit the console link provided and grant BigQuery access\n\n"

        section += "# 4. Run iterative optimization\n"
        section += "dia-harness optimize \\\n"
        section += f"  --agent-id {agent_id} \\\n"
        section += f"  --config-file {config_file} \\\n"
        section += "  --golden-set data/golden_set.xlsx \\\n"
        section += f"  --max-iterations {max_iterations} \\\n"
        section += "  --num-repeats 3 \\\n"
        section += "  --auto-accept\n\n"

        section += "# Optional: Add test dataset for overfitting detection\n"
        section += "# dia-harness optimize \\\n"
        section += f"#   --agent-id {agent_id} \\\n"
        section += f"#   --config-file {config_file} \\\n"
        section += "#   --golden-set data/golden_set.xlsx \\\n"
        section += "#   --test-set data/test_set.xlsx \\\n"
        section += f"#   --max-iterations {max_iterations} \\\n"
        section += "#   --num-repeats 3 \\\n"
        section += "#   --auto-accept\n"
        section += "```\n\n"

        # Analysis commands
        section += "### Analysis Commands\n\n"
        section += "```bash\n"

        # Use actual run_id if available
        run_dir = f"run_{timestamp}" if timestamp else "run_*"
        traj_file = f"trajectory_history_{timestamp}.json" if timestamp else "trajectory_history_*.json"

        section += "# View trajectory metrics\n"
        section += f"jq '.iterations[].evaluation.train' results/{run_dir}/{traj_file}\n\n"

        section += "# Extract average scores per iteration\n"
        section += f"jq '.iterations[] | {{iter: .iteration, score: .evaluation.train.avg_score, pass_rate: .evaluation.train.pass_rate}}' results/{run_dir}/{traj_file}\n\n"

        section += "# View failures from specific iteration (e.g., iteration 0)\n"
        section += f"jq '.iterations[0].evaluation.train.failures' results/{run_dir}/{traj_file}\n\n"

        section += "# Count error types across all results\n"
        section += f"cat results/{run_dir}/eval_train_{timestamp}.jsonl.repeat* | jq -s 'group_by(.generated_sql == \"\") | map({{no_sql: (.[0].generated_sql == \"\"), count: length}})'\n\n"

        section += "# View assist tokens for failed queries\n"
        section += f"cat results/{run_dir}/ASSIST_TOKEN_REGISTRY.md\n\n"

        section += "# Compare prompt changes across iterations\n"
        section += f"jq '.iterations[].configuration.nl2sql_prompt' results/{run_dir}/{traj_file}\n"
        section += "```\n\n"

        # Timestamp
        section += "---\n\n"
        section += f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"

        return section

    def _generate_assist_token_registry(
        self, trajectory_history: Dict, agent_id: str, run_id: str
    ) -> str:
        """Generate assist token registry for debugging.

        Args:
            trajectory_history: Optimization trajectory data
            agent_id: ID of the agent
            run_id: Run timestamp ID

        Returns:
            Path to generated registry file
        """
        iterations = trajectory_history.get("iterations", [])
        agent_name = trajectory_history.get("agent_name", "unknown")

        # Build registry content
        content = f"""# Assist Token Registry
## run_{run_id}

**Agent Name:** {agent_name}
**Agent ID:** {agent_id}
**Timestamp:** {run_id}

---

"""

        # Check if we have per-iteration eval files (new format) or single eval file (old format)
        has_per_iteration_files = any(
            self.output_dir.glob(f"eval_train_iter*_{run_id}.jsonl*")
        )

        if not has_per_iteration_files:
            # Old format: single eval file with repeats, no per-iteration files
            # Load all results from repeat files
            repeat_files = list(self.output_dir.glob(f"eval_train_{run_id}.jsonl.repeat*"))

            all_results = []
            for repeat_file in repeat_files:
                try:
                    with open(repeat_file, 'r') as f:
                        for line in f:
                            if line.strip():
                                all_results.append(json.loads(line))
                except Exception as e:
                    continue

            if all_results:
                # Categorize all results
                success_results = []
                low_score_results = []
                no_sql_results = []

                for result in all_results:
                    score_details = result.get("score_details", {})
                    total_score = score_details.get("total_score", 0)
                    generated_sql = result.get("generated_sql", "")

                    if not generated_sql or generated_sql.strip() == "":
                        no_sql_results.append(result)
                    elif total_score < 60:
                        low_score_results.append(result)
                    else:
                        success_results.append(result)

                # Write combined section (all iterations)
                total_queries = len(all_results)
                tokens_captured = sum(1 for r in all_results if self._extract_assist_token(r))

                content += f"## All Iterations Combined\n\n"
                content += f"**Total Queries:** {total_queries}\n"
                content += f"**Tokens Captured:** {tokens_captured}\n"
                content += f"**Note:** Old format - results from all iterations and repeats combined\n\n"

                # Success section
                if success_results:
                    content += f"### SUCCESS ({len(success_results)} results)\n\n"
                    for result in success_results[:50]:  # Limit to first 50
                        content += self._format_token_entry(result)
                    if len(success_results) > 50:
                        content += f"\n*... and {len(success_results) - 50} more successful results*\n\n"

                # Low score section
                if low_score_results:
                    content += f"### LOW SCORE (<60 points) ({len(low_score_results)} results)\n\n"
                    for result in low_score_results:
                        content += self._format_token_entry(result, show_error=True)

                # No SQL section
                if no_sql_results:
                    content += f"### NO SQL GENERATED ({len(no_sql_results)} results)\n\n"
                    for result in no_sql_results[:50]:  # Limit to first 50
                        content += self._format_token_entry(result, show_error=True)
                    if len(no_sql_results) > 50:
                        content += f"\n*... and {len(no_sql_results) - 50} more failures*\n\n"

        else:
            # New format: per-iteration eval files
            # Process each iteration
            for iter_data in iterations:
                iter_num = iter_data.get("iteration", 0)

                # Get evaluation results
                eval_path = self.output_dir / f"eval_train_iter{iter_num}_{run_id}.jsonl"
                if not eval_path.exists():
                    # Check for repeat files
                    repeat_files = list(self.output_dir.glob(f"eval_train_iter{iter_num}_{run_id}.jsonl.repeat*"))
                    if not repeat_files:
                        continue
                    # Use first repeat file
                    eval_path = repeat_files[0]

                # Load evaluation results
                results = []
                try:
                    with open(eval_path, 'r') as f:
                        for line in f:
                            if line.strip():
                                results.append(json.loads(line))
                except Exception as e:
                    continue

                # Categorize results
                success_results = []
                low_score_results = []
                no_sql_results = []

                for result in results:
                    score_details = result.get("score_details", {})
                    total_score = score_details.get("total_score", 0)
                    generated_sql = result.get("generated_sql", "")

                    if not generated_sql or generated_sql.strip() == "":
                        no_sql_results.append(result)
                    elif total_score < 60:
                        low_score_results.append(result)
                    else:
                        success_results.append(result)

                # Write iteration header
                total_queries = len(results)
                tokens_captured = sum(1 for r in results if self._extract_assist_token(r))

                content += f"## Iteration {iter_num}\n\n"
                content += f"**Total Queries:** {total_queries}\n"
                content += f"**Tokens Captured:** {tokens_captured}\n\n"

                # Success section
                if success_results:
                    content += f"### SUCCESS ({len(success_results)} tokens)\n\n"
                    for result in success_results:
                        content += self._format_token_entry(result)

                # Low score section
                if low_score_results:
                    content += f"### LOW SCORE (<60 points) ({len(low_score_results)} tokens)\n\n"
                    for result in low_score_results:
                        content += self._format_token_entry(result, show_error=True)

                # No SQL section
                if no_sql_results:
                    content += f"### NO SQL GENERATED ({len(no_sql_results)} tokens)\n\n"
                    for result in no_sql_results:
                        content += self._format_token_entry(result, show_error=True)

                content += "---\n\n"

        # Write registry file
        registry_path = self.output_dir / "ASSIST_TOKEN_REGISTRY.md"
        registry_path.write_text(content)

        return str(registry_path)

    def _extract_assist_token(self, result: Dict) -> Optional[str]:
        """Extract assist token from result."""
        # Try JSON field first
        if "assist_token" in result:
            return result["assist_token"]

        # Try extracting from raw_response
        raw_response = result.get("raw_response", "")
        if raw_response:
            # Convert to string if it's a dict
            if isinstance(raw_response, dict):
                raw_response = str(raw_response)

            # Extract using regex
            matches = re.findall(r"'assistToken':\s*'([^']+)'", raw_response)
            if matches:
                return matches[0]

        return None

    def _format_token_entry(self, result: Dict, show_error: bool = False) -> str:
        """Format a single token entry."""
        question = result.get("question", "Unknown question")
        question_id = result.get("question_id", "unknown")
        repeat_num = result.get("repeat_num", 1)
        score_details = result.get("score_details", {})
        total_score = score_details.get("total_score", 0)
        generated_sql = result.get("generated_sql", "")
        expected_sql = result.get("expected_sql", "")
        assist_token = self._extract_assist_token(result)

        # Truncate long questions for summary
        question_summary = question[:80] if len(question) > 80 else question

        entry = f"""<details>
<summary><b>{question_summary}</b> - Score: {total_score}/100</summary>

**Assist Token:** `{assist_token or 'Not captured'}`

**Question ID:** {question_id}

**Repeat:** {repeat_num}

"""

        if generated_sql:
            entry += f"""**Generated SQL:**
```sql
{generated_sql.strip()}
```

"""
        else:
            entry += "**Generated SQL:** *(none - NO SQL GENERATED)*\n\n"

        # Add category scores
        category_scores = score_details.get("category_scores", {})
        if category_scores:
            entry += "**Category Scores:**\n"
            entry += f"- data_source: {category_scores.get('data_source', 0)}/20\n"
            entry += f"- filtering: {category_scores.get('filtering', 0)}/25\n"
            entry += f"- columns: {category_scores.get('columns', 0)}/20\n"
            entry += f"- grouping: {category_scores.get('grouping', 0)}/15\n"
            entry += f"- ordering: {category_scores.get('ordering', 0)}/10\n"
            entry += f"- format: {category_scores.get('format', 0)}/10\n\n"

        # Show error details if requested
        if show_error:
            explanation = score_details.get("explanation", "")
            if explanation:
                entry += f"**Error Analysis:**\n{explanation[:500]}...\n\n"

            # Extract error messages from raw response
            raw_response = result.get("raw_response", "")
            if raw_response and isinstance(raw_response, str):
                error_matches = re.findall(r'"message":\s*"([^"]+)"', raw_response)
                if error_matches:
                    entry += f"**Error Message:** {error_matches[0]}\n\n"

        # Add latency if available
        latency = result.get("latency_ms")
        if latency:
            entry += f"**Latency:** {latency}ms\n\n"

        entry += "</details>\n\n"

        return entry


def main():
    """Test report generator with sample data."""
    # Sample trajectory data
    sample_trajectory = {
        "iterations": [
            {
                "iteration": 0,
                "configuration": {
                    "nl2sql_prompt": "You are a SQL expert. Generate SQL queries...",
                    "params": {"examples": []},
                },
                "evaluation": {
                    "train": {
                        "accuracy": 0.65,
                        "correct": 13,
                        "total_cases": 20,
                        "failures": [
                            {
                                "question": "What is the total revenue?",
                                "error": "SQL syntax error: missing FROM clause",
                            }
                        ],
                    },
                    "test": {"accuracy": 0.60, "correct": 6, "total_cases": 10},
                },
            },
            {
                "iteration": 1,
                "configuration": {
                    "nl2sql_prompt": "You are an expert SQL generator with schema awareness...",
                    "params": {"examples": ["Example 1", "Example 2"]},
                },
                "evaluation": {
                    "train": {
                        "accuracy": 0.80,
                        "correct": 16,
                        "total_cases": 20,
                        "failures": [],
                    },
                    "test": {"accuracy": 0.75, "correct": 7, "total_cases": 10},
                },
            },
        ]
    }

    # Generate report
    generator = OptimizationReportGenerator()
    report_path = generator.generate_report(
        trajectory_history=sample_trajectory,
        chart_paths=["results/accuracy_chart.png"],
        agent_id="test-agent-001",
    )

    print(f"Sample report generated: {report_path}")


if __name__ == "__main__":
    main()
