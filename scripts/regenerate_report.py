#!/usr/bin/env python3
"""Regenerate optimization report with existing trajectory and charts."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import directly to avoid circular imports
from iterative.report_generator import OptimizationReportGenerator


def main():
    """Regenerate report from existing trajectory and charts."""

    # Load existing trajectory
    trajectory_path = Path("results/trajectory_history_20260110_003854.json")
    print(f"Loading trajectory from: {trajectory_path}")

    with open(trajectory_path) as f:
        trajectory = json.load(f)

    # Get agent ID from trajectory
    agent_id = trajectory.get("agent_id", "unknown")
    print(f"Agent ID: {agent_id}")

    # Find all chart PNGs
    charts_dir = Path("results/charts")
    chart_paths = sorted(charts_dir.glob("*.png"))
    chart_paths_str = [str(p) for p in chart_paths]

    print(f"\nFound {len(chart_paths_str)} chart files:")
    for chart_path in chart_paths_str:
        print(f"  - {chart_path}")

    # Generate report
    generator = OptimizationReportGenerator(output_dir="results")
    report_path = generator.generate_report(
        trajectory_history=trajectory,
        chart_paths=chart_paths_str,
        agent_id=agent_id,
    )

    print(f"\nReport regenerated: {report_path}")


if __name__ == "__main__":
    main()
