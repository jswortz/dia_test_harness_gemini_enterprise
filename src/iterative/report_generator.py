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
            self._generate_opro_methodology(trajectory_history),
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

        return str(report_path)

    def _generate_header(self, agent_id: str, iteration_count: int, run_id: str) -> str:
        """Generate report header."""
        import os

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get AI models from environment
        judgement_model = os.getenv("JUDGEMENT_MODEL", "gemini-2.5-pro")
        improvement_model = os.getenv("PROMPT_IMPROVEMENT_MODEL", "gemini-3-pro-preview")
        config_model = os.getenv("CONFIG_ANALYSIS_MODEL", "gemini-3-pro-preview")

        return f"""# Agent Optimization Report

**Run ID:** `{run_id}`
**Agent ID:** `{agent_id}`
**Report Generated:** {timestamp}
**Total Iterations:** {iteration_count}
**Framework:** Data Insights Agent (DIA) Test Harness

## AI Models Used

- **Judgement Model:** {judgement_model} (SQL equivalence evaluation)
- **Prompt Improvement:** {improvement_model} (failure analysis & suggestions)
- **Config Analysis:** {config_model} (field recommendation)

## Report Features

This comprehensive optimization report includes:
- ✅ **Metrics & Charts**: Accuracy trends, metric breakdowns, and performance analysis
- ✅ **Configuration Links**: Direct links to all deployed agent configurations
- ✅ **Executions Logs**: References to log files and Cloud Console links
- ✅ **Expandable Question-Level Performance**: Click each failure to see detailed SQL comparisons and AI judgement analysis
- ✅ **Row-Level Repeat Format**: Compare scores across R1, R2, R3 repeats in single table
- ✅ **Detailed Rubric Breakdown**: 6-category scoring (Data Source, Filtering, Columns, Grouping, Ordering, Format)

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
        """Generate executive summary with key results."""
        iterations = trajectory.get("iterations", [])
        if not iterations:
            return "## Executive Summary\n\nNo iterations completed."

        # Extract metrics across iterations and track best iteration
        train_accuracies = []
        test_accuracies = []
        best_train_idx = 0
        best_train_score = 0.0

        for idx, iteration in enumerate(iterations):
            # Normalize to new format
            iteration = self._normalize_iteration(iteration)

            evals = iteration.get("evaluation", {})
            if "train" in evals:
                train_acc = evals["train"].get("accuracy", 0.0)
                train_accuracies.append(train_acc)

                # Track best iteration
                if train_acc > best_train_score:
                    best_train_score = train_acc
                    best_train_idx = idx

            if "test" in evals:
                test_accuracies.append(evals["test"].get("accuracy", 0.0))

        # Calculate improvement
        initial_train = train_accuracies[0] if train_accuracies else 0.0
        final_train = train_accuracies[-1] if train_accuracies else 0.0
        train_improvement = final_train - initial_train

        initial_test = test_accuracies[0] if test_accuracies else 0.0
        final_test = test_accuracies[-1] if test_accuracies else 0.0
        test_improvement = final_test - initial_test

        # Build summary table
        summary = f"""## Executive Summary

### Key Results

| Metric | Initial | Final | Improvement |
|--------|---------|-------|-------------|
| **Train Accuracy** | {initial_train:.2%} | {final_train:.2%} | {train_improvement:+.2%} |
"""

        if test_accuracies:
            summary += f"| **Test Accuracy** | {initial_test:.2%} | {final_test:.2%} | {test_improvement:+.2%} |\n"

        summary += f"| **Iterations** | - | {len(iterations)} | - |\n"

        # Add winning configuration callout
        start_time = trajectory.get("start_time", "")
        timestamp = ""
        if start_time:
            try:
                dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                timestamp = dt.strftime("%Y%m%d_%H%M%S")
            except:
                pass

        summary += "\n### 🏆 Best Configuration\n\n"
        summary += f"> **Iteration {best_train_idx}** achieved the highest training accuracy: **{best_train_score:.2%}**\n"
        summary += f">\n"

        if timestamp:
            config_path = f"configs/config_iteration_{best_train_idx}_final_{timestamp}.json"
            summary += f"> 📁 **Configuration File:** [`{config_path}`]({config_path})\n"
        else:
            summary += f"> 📁 **Configuration File:** `configs/config_iteration_{best_train_idx}_final_*.json`\n"

        if best_train_idx == len(iterations) - 1:
            summary += f">\n"
            summary += f"> ✅ **Status:** This is the final iteration configuration (recommended for deployment)\n"
        else:
            summary += f">\n"
            summary += f"> ℹ️ **Note:** Peak performance at iteration {best_train_idx}, but final iteration is {len(iterations)-1}\n"

        # Add ASCII chart of progress
        summary += "\n### Progress Chart\n\n```\n"
        summary += self._generate_ascii_chart(train_accuracies, "Train Accuracy")
        summary += "```\n"

        return summary

    def _generate_opro_methodology(self, trajectory: Dict) -> str:
        """Generate OPRO methodology section explaining the optimization approach."""
        iterations = trajectory.get("iterations", [])

        section = """## Optimization Methodology (OPRO-Aligned)

This optimization run uses **OPRO (Optimization by PROmpting)**, a research-backed approach from Google DeepMind for LLM-driven prompt optimization.

### Key OPRO Features

#### 1. Full Trajectory Context
- **Traditional approach:** AI sees only the current iteration's failures
- **OPRO approach:** AI sees ALL past prompts with their accuracy scores
- **Benefit:** Enables pattern recognition across full optimization history

"""

        if len(iterations) > 1:
            section += f"**In this run:** {len(iterations)} iterations captured in trajectory\n\n"
        else:
            section += "**In this run:** Single iteration (OPRO benefits start at iteration 2+)\n\n"

        section += """#### 2. Temperature Tuning
- **Setting:** Temperature = 1.0 (OPRO optimal)
- **Purpose:** Balances exploration (trying new approaches) and exploitation (refining what works)
- **Research finding:** Temperature 1.0 outperformed both conservative (0.5) and creative (1.5-2.0) settings

#### 3. Sorted Trajectory (Ascending)
- **Order:** Worst → Best performing prompts
- **Rationale:** LLMs pay more attention to end of context (recency bias)
- **Effect:** AI focuses on patterns from highest-scoring prompts

#### 4. Meta-Prompt Structure

Each iteration (2+), the AI improver receives:

```
🎯 Optimization Trajectory (Past Prompts Sorted by Accuracy)

1. Iteration 1 → Accuracy: 45.2%
   Prompt preview: "You are a data analyst..."

2. Iteration 3 → Accuracy: 52.8%
   Prompt preview: "You are a senior analyst..."

...

N. Iteration 8 → Accuracy: 68.5%
   Prompt preview: "You are an expert analyst..."

Your Goal: Generate a prompt achieving HIGHER than 68.5% accuracy.
Learn from high-scoring prompt patterns above.
```

### Research Background

**Paper:** "Large Language Models as Optimizers" (Yang et al., 2024)

**Key Results:**
- GSM8K: 71.8% → 80.2% (+8% improvement)
- BBH Tasks: +5-50% across benchmarks
- **Finding:** Full trajectory outperformed single-iteration by 15-20%

### Implementation Details

"""

        # Add statistics about this specific run
        if len(iterations) >= 2:
            # Calculate how many prompts were in trajectory for each iteration
            section += f"**Trajectory Usage:**\n"
            for idx, iteration in enumerate(iterations[1:], start=2):  # Start from iteration 2
                prompt_changes = iteration.get("prompt_changes", "")
                if "trajectory history" in prompt_changes.lower() or idx > 1:
                    # Estimate: iteration N has access to N-1 past prompts
                    num_past = min(idx - 1, 10)  # Top-10 limit
                    section += f"- Iteration {idx}: Used top {num_past} prompt(s) from history\n"
        else:
            section += "**Trajectory Usage:** N/A (requires multiple iterations)\n"

        section += """
**Top-N Filtering:**
- Maximum prompts in trajectory: 10 (configurable to 20)
- Prevents context overflow while maintaining pattern visibility

**Training Data Only:**
- All optimization uses training set failures/successes
- Test set (if provided) used only for held-out validation
- Prevents data leakage and ensures unbiased test metrics

"""

        return section

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

            # Use relative path from the report directory (output_dir)
            # The report is in output_dir, charts are in output_dir/charts/
            try:
                rel_path = path.relative_to(self.output_dir)
            except ValueError:
                # If can't make relative, just use the filename with charts/ prefix
                rel_path = Path("charts") / path.name

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
            section += f"\n**AI Models Used:**\n"
            section += f"- **SQL Judgement**: Gemini 2.5 Pro (for semantic SQL equivalence evaluation)\n"
            section += f"- **Prompt Improvement**: Gemini 2.0 Flash Exp (for analyzing failures and suggesting improvements)\n"
            section += f"- **Config Analysis**: Gemini 2.0 Flash Exp (for recommending configuration changes)\n"

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
        """Format detailed results table with rubric breakdown per question and repeat.

        Args:
            iteration: Iteration data containing all test results
            eval_data: Evaluation data with failures and successes

        Returns:
            Markdown table with detailed rubric scores per question and repeat
        """
        import json

        # Try to load detailed results from eval files
        iter_num = iteration.get("iteration", 0)
        run_id = self.output_dir.name.replace('run_', '')

        # Look for per-iteration eval files first (new format)
        eval_file_pattern = f"eval_train_iter{iter_num}_{run_id}.jsonl"
        repeat_files = sorted(self.output_dir.glob(f"{eval_file_pattern}.repeat*"))

        # Fallback to old format (single eval file with all iterations)
        if not repeat_files:
            repeat_files = sorted(self.output_dir.glob(f"eval_train_{run_id}.jsonl.repeat*"))

        if not repeat_files:
            # No detailed results available, use old simple table
            all_results = iteration.get("results", [])
            if not all_results:
                return "\n**Results Table:** No detailed test results available\n\n"
            return self._format_simple_results_table(all_results)

        # Load all repeat results
        all_repeat_results = {}
        for repeat_file in repeat_files:
            repeat_num = int(repeat_file.name.split('repeat')[-1])
            results = []
            try:
                with open(repeat_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            results.append(json.loads(line))
                all_repeat_results[repeat_num] = results
            except Exception as e:
                continue

        if not all_repeat_results:
            return "\n**Results Table:** No detailed test results available\n\n"

        # Generate rubric-focused table with color-coded feedback
        section = "\n### Detailed Question-Level Results\n\n"

        # Get all unique questions from first repeat
        first_repeat = all_repeat_results[sorted(all_repeat_results.keys())[0]]
        num_questions = len(first_repeat)
        num_repeats = len(all_repeat_results)

        # Calculate overall summary stats
        total_avg_score = 0
        total_queries = 0

        for repeat_num, results in all_repeat_results.items():
            for result in results:
                total_avg_score += result.get('score_details', {}).get('total_score', 0)
                total_queries += 1

        overall_avg = total_avg_score / total_queries if total_queries > 0 else 0
        section += f"**Overall Summary:** Average Score: {overall_avg:.1f}/100 across {num_repeats} repeats ({total_queries} total queries)\n\n"

        # Helper function to color-code scores
        def color_code_score(score, max_score):
            """Return emoji indicator based on score performance."""
            if score == 0:
                return "⚫"  # Not attempted or no SQL
            pct = (score / max_score) if max_score > 0 else 0
            if pct >= 0.9:
                return "🟢"  # Excellent
            elif pct >= 0.7:
                return "🟡"  # Good
            elif pct >= 0.5:
                return "🟠"  # Partial
            else:
                return "🔴"  # Poor

        # Rubric-focused table with embedded repeats
        section += "#### Rubric Category Performance (All Repeats)\n\n"

        # Build header with rubric categories
        section += "| # | Question | R# | Total | DS | Filt | Col | Grp | Ord | Fmt |\n"
        section += "|---|----------|-------|-------|----|----|----|----|----|----|\n"

        # Organize results by question
        for q_idx in range(num_questions):
            # Get question from first repeat
            question = first_repeat[q_idx].get('question', 'Unknown')[:35]

            # Show each repeat as a separate sub-row
            for repeat_num in sorted(all_repeat_results.keys()):
                results = all_repeat_results[repeat_num]
                if q_idx < len(results):
                    result = results[q_idx]
                    score_details = result.get('score_details', {})
                    total_score = score_details.get('total_score', 0)
                    category_scores = score_details.get('category_scores', {})

                    # Extract category scores
                    ds = category_scores.get('data_source', 0)
                    filt = category_scores.get('filtering', 0)
                    col = category_scores.get('columns', 0)
                    grp = category_scores.get('grouping', 0)
                    ord = category_scores.get('ordering', 0)
                    fmt = category_scores.get('format', 0)

                    # Color code each category
                    ds_str = f"{color_code_score(ds, 20)} {ds}/20"
                    filt_str = f"{color_code_score(filt, 25)} {filt}/25"
                    col_str = f"{color_code_score(col, 20)} {col}/20"
                    grp_str = f"{color_code_score(grp, 15)} {grp}/15"
                    ord_str = f"{color_code_score(ord, 10)} {ord}/10"
                    fmt_str = f"{color_code_score(fmt, 10)} {fmt}/10"

                    # Overall score color
                    total_color = color_code_score(total_score, 100)

                    # Only show question text on first repeat row
                    if repeat_num == sorted(all_repeat_results.keys())[0]:
                        q_text = f"{question}"
                    else:
                        q_text = '""'

                    section += f"| {q_idx+1} | {q_text} | R{repeat_num} | {total_color} {total_score}/100 | {ds_str} | {filt_str} | {col_str} | {grp_str} | {ord_str} | {fmt_str} |\n"

            # Add average row after all repeats
            if num_repeats > 1:
                # Calculate averages across repeats (excluding errors/missing measurements)
                avg_total = 0
                avg_ds = 0
                avg_filt = 0
                avg_col = 0
                avg_grp = 0
                avg_ord = 0
                avg_fmt = 0
                valid_count = 0  # Count of non-error repeats

                for repeat_num in sorted(all_repeat_results.keys()):
                    results = all_repeat_results[repeat_num]
                    if q_idx < len(results):
                        result = results[q_idx]

                        # Skip if this repeat had an error (treat as missing data)
                        if 'error' in result:
                            continue

                        score_details = result.get('score_details', {})
                        avg_total += score_details.get('total_score', 0)
                        category_scores = score_details.get('category_scores', {})
                        avg_ds += category_scores.get('data_source', 0)
                        avg_filt += category_scores.get('filtering', 0)
                        avg_col += category_scores.get('columns', 0)
                        avg_grp += category_scores.get('grouping', 0)
                        avg_ord += category_scores.get('ordering', 0)
                        avg_fmt += category_scores.get('format', 0)
                        valid_count += 1

                # Only divide by valid measurements, not total repeats
                if valid_count > 0:
                    avg_total = avg_total / valid_count
                    avg_ds = avg_ds / valid_count
                    avg_filt = avg_filt / valid_count
                    avg_col = avg_col / valid_count
                    avg_grp = avg_grp / valid_count
                    avg_ord = avg_ord / valid_count
                    avg_fmt = avg_fmt / valid_count
                else:
                    # All repeats had errors - set to 0
                    avg_total = avg_ds = avg_filt = avg_col = avg_grp = avg_ord = avg_fmt = 0

                # Color code averages
                total_color = color_code_score(avg_total, 100)
                ds_str = f"{color_code_score(avg_ds, 20)} {avg_ds:.0f}/20"
                filt_str = f"{color_code_score(avg_filt, 25)} {avg_filt:.0f}/25"
                col_str = f"{color_code_score(avg_col, 20)} {avg_col:.0f}/20"
                grp_str = f"{color_code_score(avg_grp, 15)} {avg_grp:.0f}/15"
                ord_str = f"{color_code_score(avg_ord, 10)} {avg_ord:.0f}/10"
                fmt_str = f"{color_code_score(avg_fmt, 10)} {avg_fmt:.0f}/10"

                section += f"| | *Avg* | **μ** | {total_color} **{avg_total:.0f}/100** | {ds_str} | {filt_str} | {col_str} | {grp_str} | {ord_str} | {fmt_str} |\n"

                # Add visual separator between question groups
                if q_idx < num_questions - 1:
                    section += "| | | | | | | | | | |\n"

        section += "\n**Column Legend:**\n"
        section += "- **R#** = Repeat number (R1, R2, R3)\n"
        section += "- **Total** = Overall score out of 100\n"
        section += "- **DS** = Data Source (max 20 pts)\n"
        section += "- **Filt** = Filtering Logic (max 25 pts)\n"
        section += "- **Col** = Column Selection (max 20 pts)\n"
        section += "- **Grp** = Grouping & Granularity (max 15 pts)\n"
        section += "- **Ord** = Ordering & Limits (max 10 pts)\n"
        section += "- **Fmt** = Output Format (max 10 pts)\n"
        section += "- **μ** = Average across repeats\n\n"

        section += "**Color Coding:**\n"
        section += "- 🟢 Excellent (≥90%) | 🟡 Good (70-89%) | 🟠 Partial (50-69%) | 🔴 Poor (<50%) | ⚫ No SQL\n\n"

        # Add cross-repeat aggregated summary
        section += "#### Aggregated Summary (All Repeats)\n\n"

        # Collect all questions and their scores across repeats
        question_aggregates = {}
        for repeat_num, results in all_repeat_results.items():
            for result in results:
                q_id = result.get('question_id', result.get('question', ''))
                question = result.get('question', 'Unknown')
                score = result.get('score_details', {}).get('total_score', 0)

                if q_id not in question_aggregates:
                    question_aggregates[q_id] = {
                        'question': question,
                        'scores': []
                    }

                question_aggregates[q_id]['scores'].append(score)

        section += "| Question | Avg Score | Min | Max | σ |\n"
        section += "|----------|-----------|-----|-----|---|\n"

        for q_id, agg in question_aggregates.items():
            question = agg['question'][:50]
            scores = agg['scores']
            avg_score = sum(scores) / len(scores) if scores else 0
            min_score = min(scores) if scores else 0
            max_score = max(scores) if scores else 0
            std_dev = (sum((x - avg_score) ** 2 for x in scores) / len(scores)) ** 0.5 if len(scores) > 1 else 0

            section += f"| {question} | {avg_score:.1f} | {min_score} | {max_score} | {std_dev:.1f} |\n"

        section += "\n"

        return section

    def _format_simple_results_table(self, all_results: list) -> str:
        """Format simple results table when detailed data not available."""
        section = "\n**Question-Level Results:**\n\n"
        section += "| # | Question | Status | Match Type |\n"
        section += "|---|----------|--------|------------|\n"

        for i, result in enumerate(all_results, 1):
            question = result.get("question", "Unknown")[:60]
            is_match = result.get("is_match", False)
            explanation = result.get("explanation", "")
            issue = result.get("issue", result.get("error", "Unknown"))

            if is_match:
                status = "🟢 Exact"
                match_type = "Exact Match"
            elif "EQUIVALENT" in explanation:
                status = "🟡 Equivalent"
                match_type = "Semantic Match"
            elif "DIFFERENT" in explanation or not is_match:
                status = "🔴 Different"
                if issue and issue != "Unknown" and issue != "Unknown error":
                    match_type = issue[:30] + "..." if len(issue) > 30 else issue
                else:
                    match_type = "Different SQL"
            else:
                status = "⚪ Unknown"
                match_type = issue[:30] if issue else "Unknown"

            section += f"| {i} | {question} | {status} | {match_type} |\n"

        total = len(all_results)
        exact_matches = sum(1 for r in all_results if r.get("is_match", False))
        semantic_matches = sum(1 for r in all_results if not r.get("is_match", False) and "EQUIVALENT" in r.get("explanation", ""))
        different = total - exact_matches - semantic_matches

        section += f"\n**Summary:** {total} tests | "
        section += f"🟢 {exact_matches} exact | "
        section += f"🟡 {semantic_matches} semantic | "
        section += f"🔴 {different} different\n\n"

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

                # Get most descriptive error message
                error = failure.get("error", "")
                issue = failure.get("issue", "")
                explanation = failure.get("explanation", "")
                expected_sql = failure.get("expected_sql", "")
                generated_sql = failure.get("generated_sql", "")

                # Determine best error description
                if explanation and "Category" in explanation:
                    # Extract verdict from explanation
                    if "COMPLETELY_WRONG" in explanation:
                        error_summary = "Completely wrong SQL logic"
                    elif "PARTIALLY_CORRECT" in explanation:
                        error_summary = "Partially correct (low rubric scores)"
                    elif "MOSTLY_CORRECT" in explanation:
                        error_summary = "Mostly correct (minor issues)"
                    else:
                        error_summary = "Failed rubric criteria"
                elif not generated_sql or generated_sql.strip() == "":
                    # Check for OAuth authorization errors
                    if error and "OAuth authorization" in error:
                        error_summary = "Agent requires OAuth authorization (setup required)"
                    elif issue and "OAuth authorization" in issue:
                        error_summary = "Agent requires OAuth authorization (setup required)"
                    elif error:
                        error_summary = f"No SQL generated: {error}"
                    elif issue:
                        error_summary = f"No SQL generated: {issue}"
                    else:
                        error_summary = "No SQL generated"
                elif issue and issue != "Unknown" and issue != "Unknown error":
                    error_summary = issue
                elif error and error != "Unknown" and error != "Unknown error":
                    error_summary = error
                else:
                    error_summary = "SQL mismatch"

                # Create expandable section
                section += f"<details>\n"
                section += f"<summary><b>{i+1}. {question}</b> - <i>{error_summary[:80]}</i></summary>\n\n"
                section += f"**Issue:** {error_summary}\n\n"

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
                error = failure.get("error", "Unknown error")

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

        # Expanded table with all config fields
        section += "| Iter | Train | Test | Prompt | Schema | Examples | Py Prompt | Tables |\n"
        section += "|------|-------|------|--------|--------|----------|-----------|--------|\n"

        for idx, iteration in enumerate(iterations):
            # Normalize to new format
            iteration = self._normalize_iteration(iteration)

            evals = iteration.get("evaluation", {})
            config = iteration.get("configuration", iteration.get("config", {}))  # Backward compatible

            train_acc = evals.get("train", {}).get("accuracy", 0.0)
            test_acc = evals.get("test", {}).get("accuracy", 0.0)

            # Config field summaries
            prompt_len = len(config.get("nl2sql_prompt", ""))
            schema_len = len(str(config.get("schema_description", ""))) if config.get("schema_description") else 0
            num_examples = len(config.get("nl2sql_examples", []))
            py_prompt_set = "Yes" if config.get("nl2py_prompt") else "No"

            # Table access
            allowed = len(config.get("allowed_tables", []))
            blocked = len(config.get("blocked_tables", []))
            tables_str = f"A:{allowed}/B:{blocked}" if (allowed or blocked) else "All"

            section += (
                f"| {idx} | {train_acc:.1%} | {test_acc:.1%} | "
                f"{prompt_len}ch | {schema_len}ch | {num_examples}ex | "
                f"{py_prompt_set} | {tables_str} |\n"
            )

        # Add legend
        section += "\n**Legend:**\n"
        section += "- Prompt/Schema: Character count\n"
        section += "- Examples: Number of few-shot examples (ex)\n"
        section += "- Py Prompt: Whether nl2py_prompt is set\n"
        section += "- Tables: A=Allowed count, B=Blocked count\n"

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
            section += f"- [`trajectory_history_{timestamp}.json`](trajectory_history_{timestamp}.json) - Complete optimization trajectory\n"
            section += f"- [`eval_train_{timestamp}.jsonl.repeat1`](eval_train_{timestamp}.jsonl.repeat1) - Training evaluation (repeat 1)\n"
            section += f"- [`eval_train_{timestamp}.jsonl.repeat2`](eval_train_{timestamp}.jsonl.repeat2) - Training evaluation (repeat 2)\n\n"
        else:
            section += f"- `results/trajectory_history_{agent_id}.json` - Complete optimization trajectory\n"
            section += "- `results/eval_train_*.jsonl.repeat*` - Evaluation results\n\n"

        # Add log file links
        section += "**Execution Logs:**\n"
        section += "- Check results directory for phase1/phase2 test output logs\n"
        section += "- Agent deployment logs available via Google Cloud Console\n"
        section += "- [View agent in Cloud Console](https://console.cloud.google.com/gen-app-builder/engines)\n\n"

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
        section += "- [`charts/accuracy_over_time.png`](charts/accuracy_over_time.png) - Accuracy progression\n"
        section += "- [`charts/metric_breakdown.png`](charts/metric_breakdown.png) - Metrics breakdown\n"
        section += "- [`charts/improvement_deltas.png`](charts/improvement_deltas.png) - Iteration-to-iteration changes\n"
        section += "- [`charts/question_heatmap.png`](charts/question_heatmap.png) - Per-question performance (if available)\n\n"

        # Reproduction commands
        section += "### Reproduction Commands\n\n"
        section += "To reproduce this optimization run:\n\n"
        section += "```bash\n"
        section += "# Set up environment\n"
        section += "source .venv/bin/activate\n"
        section += "export GOOGLE_CLOUD_PROJECT=your-project-id\n\n"

        section += "# Run iterative optimization\n"
        section += "python scripts/run_iterative_optimizer.py \\\n"
        section += f"  --agent-id {agent_id} \\\n"
        section += "  --train-set data/golden_set.json \\\n"
        section += "  --test-set data/test_set.json \\\n"
        section += "  --max-iterations 10 \\\n"
        section += "  --repeat-measurements 3\n"
        section += "```\n\n"

        # Analysis commands
        section += "### Analysis Commands\n\n"
        section += "```bash\n"
        section += "# View detailed iteration results\n"
        section += "cat results/iteration_*.json | jq '.evaluation.train.accuracy'\n\n"

        section += "# Extract all failure cases\n"
        section += "cat results/trajectory_history_*.json | jq '.iterations[].evaluation.train.failures'\n\n"

        section += "# Compare configurations\n"
        section += "cat results/trajectory_history_*.json | jq '.iterations[].configuration.nl2sql_prompt'\n"
        section += "```\n\n"

        # Timestamp
        section += "---\n\n"
        section += f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"

        return section


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
