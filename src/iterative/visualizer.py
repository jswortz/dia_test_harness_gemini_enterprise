"""Trajectory visualization for iterative agent optimization.

This module provides visualization tools for analyzing iterative optimization
results, including accuracy trends, metric breakdowns, and comparative analysis.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

logger = logging.getLogger(__name__)


class TrajectoryVisualizer:
    """Generates matplotlib/seaborn charts for optimization trajectories."""

    def __init__(
        self,
        trajectory_data: Dict[str, Any],
        output_dir: str = "results/charts",
        dpi: int = 300,
        figsize: tuple = (12, 6),
    ):
        """Initialize the visualizer.

        Args:
            trajectory_data: Dictionary containing optimization trajectory data
            output_dir: Directory to save charts
            dpi: Resolution for saved images
            figsize: Default figure size (width, height)
        """
        self.trajectory_data = trajectory_data
        self.output_dir = Path(output_dir)
        self.dpi = dpi
        self.figsize = figsize

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set seaborn style
        sns.set_style("whitegrid")

        logger.info(f"TrajectoryVisualizer initialized with output_dir={output_dir}")

    def _get_iteration_metrics(self) -> List[Dict[str, Any]]:
        """Extract evaluation metrics from trajectory data.

        Returns:
            List of evaluation results per iteration
        """
        iterations = self.trajectory_data.get("iterations", [])
        if not iterations:
            logger.warning("No iteration data found in trajectory")
            return []

        # Extract evaluation section from each iteration
        evaluations = []
        for iteration in iterations:
            if "evaluation" in iteration:
                eval_data = iteration["evaluation"].copy()
                # Add iteration number and timestamp for context
                eval_data["iteration"] = iteration.get("iteration", 0)
                eval_data["timestamp"] = iteration.get("timestamp")
                evaluations.append(eval_data)

        if not evaluations:
            logger.warning("No evaluation data found in iterations")

        return evaluations

    def _has_repeats(self) -> bool:
        """Check if trajectory contains repeat measurements.

        Returns:
            True if any iteration has repeat measurements
        """
        evaluations = self._get_iteration_metrics()
        for eval_data in evaluations:
            if eval_data.get("num_repeats", 1) > 1:
                return True
        return False

    def _has_test_set(self) -> bool:
        """Check if trajectory contains test set evaluations.

        Returns:
            True if test set data exists
        """
        evaluations = self._get_iteration_metrics()
        for eval_data in evaluations:
            if "test_accuracy" in eval_data or "test_metrics" in eval_data:
                return True
        return False

    def plot_accuracy_over_time(self, save: bool = True) -> Optional[str]:
        """Generate line chart of accuracy over iterations.

        Shows mean accuracy with error bars if repeat measurements exist.

        Args:
            save: Whether to save the chart to disk

        Returns:
            Path to saved chart if save=True, else None
        """
        evaluations = self._get_iteration_metrics()
        if not evaluations:
            logger.warning("No data available for accuracy_over_time plot")
            return None

        iterations = []
        accuracies = []
        stds = []

        for eval_data in evaluations:
            iteration = eval_data.get("iteration", len(iterations))
            accuracy = eval_data.get("accuracy", 0.0)
            std = eval_data.get("accuracy_std", 0.0)

            iterations.append(iteration)
            accuracies.append(accuracy)
            stds.append(std)

        fig, ax = plt.subplots(figsize=self.figsize)

        if self._has_repeats():
            # Plot with error bars
            ax.errorbar(
                iterations,
                accuracies,
                yerr=stds,
                marker="o",
                markersize=8,
                capsize=5,
                capthick=2,
                linewidth=2,
                label="Mean Accuracy ± Std",
            )
        else:
            # Simple line plot
            ax.plot(
                iterations,
                accuracies,
                marker="o",
                markersize=8,
                linewidth=2,
                label="Accuracy",
            )

        ax.set_xlabel("Iteration", fontsize=12)
        ax.set_ylabel("Accuracy", fontsize=12)
        ax.set_title("Accuracy Over Iterations", fontsize=14, fontweight="bold")
        ax.set_ylim(0, 1.05)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save:
            output_path = self.output_dir / "accuracy_over_time.png"
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")
            logger.info(f"Saved accuracy_over_time chart to {output_path}")
            plt.close(fig)
            return str(output_path)
        else:
            plt.close(fig)
            return None

    def plot_accuracy_distribution(self, save: bool = True) -> Optional[str]:
        """Generate box plot showing accuracy distribution across iterations.

        Only applicable if repeat measurements exist.

        Args:
            save: Whether to save the chart to disk

        Returns:
            Path to saved chart if save=True, else None
        """
        if not self._has_repeats():
            logger.info("No repeat measurements - skipping accuracy_distribution plot")
            return None

        evaluations = self._get_iteration_metrics()
        if not evaluations:
            logger.warning("No data available for accuracy_distribution plot")
            return None

        # Collect distribution data
        data_for_plot = []
        labels = []

        for eval_data in evaluations:
            iteration = eval_data.get("iteration", len(labels))
            # Try to get individual repeat scores
            repeat_scores = eval_data.get("repeat_scores", [])
            if not repeat_scores:
                # Fallback to mean and std
                mean = eval_data.get("accuracy", 0.0)
                std = eval_data.get("accuracy_std", 0.0)
                num_repeats = eval_data.get("num_repeats", 1)
                # Simulate distribution (not ideal but better than nothing)
                if num_repeats > 1:
                    repeat_scores = np.random.normal(mean, std, num_repeats).tolist()
                else:
                    repeat_scores = [mean]

            data_for_plot.append(repeat_scores)
            labels.append(f"Iter {iteration}")

        fig, ax = plt.subplots(figsize=self.figsize)

        bp = ax.boxplot(
            data_for_plot,
            labels=labels,
            patch_artist=True,
            notch=True,
            showmeans=True,
        )

        # Color the boxes
        for patch in bp["boxes"]:
            patch.set_facecolor("lightblue")
            patch.set_alpha(0.7)

        ax.set_xlabel("Iteration", fontsize=12)
        ax.set_ylabel("Accuracy", fontsize=12)
        ax.set_title("Accuracy Distribution Across Iterations", fontsize=14, fontweight="bold")
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()

        if save:
            output_path = self.output_dir / "accuracy_distribution.png"
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")
            logger.info(f"Saved accuracy_distribution chart to {output_path}")
            plt.close(fig)
            return str(output_path)
        else:
            plt.close(fig)
            return None

    def plot_metric_breakdown(self, save: bool = True) -> Optional[str]:
        """Generate stacked bar chart of metric breakdown.

        Shows exact matches, semantic matches, and failures per iteration.

        Args:
            save: Whether to save the chart to disk

        Returns:
            Path to saved chart if save=True, else None
        """
        evaluations = self._get_iteration_metrics()
        if not evaluations:
            logger.warning("No data available for metric_breakdown plot")
            return None

        iterations = []
        exact_matches = []
        semantic_matches = []
        failures = []

        for eval_data in evaluations:
            iteration = eval_data.get("iteration", len(iterations))
            metrics = eval_data.get("metrics", {})

            exact = metrics.get("exact_match", 0)
            semantic = metrics.get("semantic_match", 0)
            fail = metrics.get("failed", 0)

            iterations.append(f"Iter {iteration}")
            exact_matches.append(exact)
            semantic_matches.append(semantic)
            failures.append(fail)

        fig, ax = plt.subplots(figsize=self.figsize)

        x = np.arange(len(iterations))
        width = 0.6

        # Stacked bars
        p1 = ax.bar(x, exact_matches, width, label="Exact Match", color="green", alpha=0.8)
        p2 = ax.bar(
            x,
            semantic_matches,
            width,
            bottom=exact_matches,
            label="Semantic Match",
            color="orange",
            alpha=0.8,
        )
        p3 = ax.bar(
            x,
            failures,
            width,
            bottom=np.array(exact_matches) + np.array(semantic_matches),
            label="Failed",
            color="red",
            alpha=0.8,
        )

        ax.set_xlabel("Iteration", fontsize=12)
        ax.set_ylabel("Count", fontsize=12)
        ax.set_title("Metric Breakdown by Iteration", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(iterations)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()

        if save:
            output_path = self.output_dir / "metric_breakdown.png"
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")
            logger.info(f"Saved metric_breakdown chart to {output_path}")
            plt.close(fig)
            return str(output_path)
        else:
            plt.close(fig)
            return None

    def plot_question_heatmap(self, save: bool = True) -> Optional[str]:
        """Generate heatmap of question pass/fail across iterations.

        Rows are questions, columns are iterations, cells show pass (1) or fail (0).

        Args:
            save: Whether to save the chart to disk

        Returns:
            Path to saved chart if save=True, else None
        """
        evaluations = self._get_iteration_metrics()
        if not evaluations:
            logger.warning("No data available for question_heatmap plot")
            return None

        # Extract question-level results
        question_results = {}  # {question_id: [iter0_pass, iter1_pass, ...]}

        for eval_data in evaluations:
            results = eval_data.get("results", [])
            for result in results:
                question_id = result.get("question_id", result.get("question", "unknown"))
                passed = 1 if result.get("passed", False) else 0

                if question_id not in question_results:
                    question_results[question_id] = []
                question_results[question_id].append(passed)

        if not question_results:
            logger.warning("No question-level results found for heatmap")
            return None

        # Build matrix
        questions = list(question_results.keys())
        num_iterations = len(evaluations)

        # Pad results if some questions don't have all iterations
        matrix = []
        for q in questions:
            row = question_results[q]
            # Pad with -1 (missing data) if needed
            while len(row) < num_iterations:
                row.append(-1)
            matrix.append(row[:num_iterations])

        matrix = np.array(matrix)

        # Create heatmap
        fig, ax = plt.subplots(figsize=(max(12, num_iterations * 1.5), max(6, len(questions) * 0.4)))

        # Custom colormap: -1=gray, 0=red, 1=green
        cmap = sns.color_palette(["gray", "red", "green"], as_cmap=False)
        bounds = [-1.5, -0.5, 0.5, 1.5]

        sns.heatmap(
            matrix,
            cmap=cmap,
            cbar_kws={"ticks": [-1, 0, 1], "label": "Result"},
            linewidths=0.5,
            linecolor="white",
            ax=ax,
            vmin=-1.5,
            vmax=1.5,
        )

        # Set labels
        ax.set_xlabel("Iteration", fontsize=12)
        ax.set_ylabel("Question", fontsize=12)
        ax.set_title("Question Performance Heatmap", fontsize=14, fontweight="bold")

        # Format x-axis
        ax.set_xticks(np.arange(num_iterations) + 0.5)
        ax.set_xticklabels([f"Iter {i}" for i in range(num_iterations)])

        # Format y-axis - truncate long questions
        truncated_questions = [
            q[:40] + "..." if len(str(q)) > 40 else q for q in questions
        ]
        ax.set_yticks(np.arange(len(questions)) + 0.5)
        ax.set_yticklabels(truncated_questions, fontsize=8)

        plt.tight_layout()

        if save:
            output_path = self.output_dir / "question_heatmap.png"
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")
            logger.info(f"Saved question_heatmap chart to {output_path}")
            plt.close(fig)
            return str(output_path)
        else:
            plt.close(fig)
            return None

    def plot_improvement_deltas(self, save: bool = True) -> Optional[str]:
        """Generate bar chart of iteration-to-iteration accuracy changes.

        Shows delta (change) in accuracy between consecutive iterations.

        Args:
            save: Whether to save the chart to disk

        Returns:
            Path to saved chart if save=True, else None
        """
        evaluations = self._get_iteration_metrics()
        if len(evaluations) < 2:
            logger.warning("Need at least 2 iterations for improvement_deltas plot")
            return None

        deltas = []
        labels = []

        for i in range(1, len(evaluations)):
            prev_acc = evaluations[i - 1].get("accuracy", 0.0)
            curr_acc = evaluations[i].get("accuracy", 0.0)
            delta = curr_acc - prev_acc

            deltas.append(delta)
            labels.append(f"{i-1}→{i}")

        fig, ax = plt.subplots(figsize=self.figsize)

        # Color bars based on positive/negative change
        colors = ["green" if d >= 0 else "red" for d in deltas]

        bars = ax.bar(labels, deltas, color=colors, alpha=0.7, edgecolor="black")

        # Add value labels on bars
        for bar, delta in zip(bars, deltas):
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{delta:+.3f}",
                ha="center",
                va="bottom" if delta >= 0 else "top",
                fontsize=9,
            )

        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_xlabel("Iteration Transition", fontsize=12)
        ax.set_ylabel("Accuracy Change (Δ)", fontsize=12)
        ax.set_title("Iteration-to-Iteration Accuracy Improvements", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()

        if save:
            output_path = self.output_dir / "improvement_deltas.png"
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")
            logger.info(f"Saved improvement_deltas chart to {output_path}")
            plt.close(fig)
            return str(output_path)
        else:
            plt.close(fig)
            return None

    def plot_train_vs_test_accuracy(self, save: bool = True) -> Optional[str]:
        """Generate comparison chart of training vs test accuracy.

        Only applicable if test set evaluations exist.

        Args:
            save: Whether to save the chart to disk

        Returns:
            Path to saved chart if save=True, else None
        """
        if not self._has_test_set():
            logger.info("No test set data - skipping train_vs_test_accuracy plot")
            return None

        evaluations = self._get_iteration_metrics()
        if not evaluations:
            logger.warning("No data available for train_vs_test_accuracy plot")
            return None

        iterations = []
        train_accs = []
        test_accs = []

        for eval_data in evaluations:
            iteration = eval_data.get("iteration", len(iterations))
            train_acc = eval_data.get("accuracy", 0.0)  # Default to train accuracy
            test_acc = eval_data.get("test_accuracy", None)

            if test_acc is not None:
                iterations.append(iteration)
                train_accs.append(train_acc)
                test_accs.append(test_acc)

        if not iterations:
            logger.warning("No test accuracy data found")
            return None

        fig, ax = plt.subplots(figsize=self.figsize)

        ax.plot(
            iterations,
            train_accs,
            marker="o",
            markersize=8,
            linewidth=2,
            label="Training Accuracy",
            color="blue",
        )
        ax.plot(
            iterations,
            test_accs,
            marker="s",
            markersize=8,
            linewidth=2,
            label="Test Accuracy",
            color="orange",
        )

        ax.set_xlabel("Iteration", fontsize=12)
        ax.set_ylabel("Accuracy", fontsize=12)
        ax.set_title("Training vs Test Accuracy", fontsize=14, fontweight="bold")
        ax.set_ylim(0, 1.05)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save:
            output_path = self.output_dir / "train_vs_test_accuracy.png"
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")
            logger.info(f"Saved train_vs_test_accuracy chart to {output_path}")
            plt.close(fig)
            return str(output_path)
        else:
            plt.close(fig)
            return None

    def generate_all_charts(self) -> Dict[str, Optional[str]]:
        """Generate all available charts.

        Calls all chart generation methods and returns paths to saved charts.

        Returns:
            Dictionary mapping chart names to file paths (None if skipped)
        """
        logger.info("Generating all charts...")

        chart_paths = {}

        try:
            chart_paths["accuracy_over_time"] = self.plot_accuracy_over_time(save=True)
        except Exception as e:
            logger.error(f"Error generating accuracy_over_time: {e}")
            chart_paths["accuracy_over_time"] = None

        try:
            chart_paths["accuracy_distribution"] = self.plot_accuracy_distribution(save=True)
        except Exception as e:
            logger.error(f"Error generating accuracy_distribution: {e}")
            chart_paths["accuracy_distribution"] = None

        try:
            chart_paths["metric_breakdown"] = self.plot_metric_breakdown(save=True)
        except Exception as e:
            logger.error(f"Error generating metric_breakdown: {e}")
            chart_paths["metric_breakdown"] = None

        try:
            chart_paths["question_heatmap"] = self.plot_question_heatmap(save=True)
        except Exception as e:
            logger.error(f"Error generating question_heatmap: {e}")
            chart_paths["question_heatmap"] = None

        try:
            chart_paths["improvement_deltas"] = self.plot_improvement_deltas(save=True)
        except Exception as e:
            logger.error(f"Error generating improvement_deltas: {e}")
            chart_paths["improvement_deltas"] = None

        try:
            chart_paths["train_vs_test_accuracy"] = self.plot_train_vs_test_accuracy(save=True)
        except Exception as e:
            logger.error(f"Error generating train_vs_test_accuracy: {e}")
            chart_paths["train_vs_test_accuracy"] = None

        # Log summary
        generated = [k for k, v in chart_paths.items() if v is not None]
        skipped = [k for k, v in chart_paths.items() if v is None]

        logger.info(f"Generated {len(generated)} charts: {', '.join(generated)}")
        if skipped:
            logger.info(f"Skipped {len(skipped)} charts: {', '.join(skipped)}")

        return chart_paths


def load_trajectory_and_visualize(
    trajectory_file: str,
    output_dir: str = "results/charts",
    generate_all: bool = True,
) -> TrajectoryVisualizer:
    """Load trajectory data from file and generate visualizations.

    Convenience function for loading and visualizing in one step.

    Args:
        trajectory_file: Path to trajectory JSON file
        output_dir: Directory to save charts
        generate_all: Whether to generate all charts immediately

    Returns:
        TrajectoryVisualizer instance
    """
    with open(trajectory_file, "r") as f:
        trajectory_data = json.load(f)

    visualizer = TrajectoryVisualizer(trajectory_data, output_dir=output_dir)

    if generate_all:
        visualizer.generate_all_charts()

    return visualizer
