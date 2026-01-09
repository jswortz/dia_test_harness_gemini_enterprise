#!/usr/bin/env python3
"""
Test script to verify chart generation from trajectory data.
"""

import json
import sys
import os

sys.path.insert(0, 'src')

from iterative.visualizer import TrajectoryVisualizer


def main():
    # Find most recent trajectory file
    import glob
    trajectory_files = glob.glob('results/trajectory_history_*.json')
    if not trajectory_files:
        print("❌ No trajectory files found in results/")
        return 1

    trajectory_file = sorted(trajectory_files)[-1]
    print(f"Loading trajectory: {trajectory_file}\n")

    # Load trajectory data
    with open(trajectory_file) as f:
        data = json.load(f)

    print("Trajectory structure:")
    print(f"  Agent: {data.get('agent_name')}")
    print(f"  Start: {data.get('start_time')}")
    print(f"  Iterations: {len(data.get('iterations', []))}")

    if data.get('iterations'):
        print(f"\nFirst iteration structure:")
        first_iter = data['iterations'][0]
        print(f"  Has 'evaluation': {'evaluation' in first_iter}")
        if 'evaluation' in first_iter:
            eval_data = first_iter['evaluation']
            print(f"  Has 'train': {'train' in eval_data}")
            print(f"  Has 'test': {'test' in eval_data}")
            if 'train' in eval_data:
                print(f"  Train keys: {list(eval_data['train'].keys())}")

    print(f"\n{'='*80}")
    print("GENERATING CHARTS")
    print(f"{'='*80}\n")

    # Create visualizer with test output directory
    viz = TrajectoryVisualizer(data, output_dir="results/test_charts")

    # Generate all charts
    paths = viz.generate_all_charts()

    print(f"\n{'='*80}")
    print("RESULTS")
    print(f"{'='*80}\n")

    generated = [name for name, path in paths.items() if path]
    skipped = [name for name, path in paths.items() if not path]

    print(f"Generated {len(generated)}/{len(paths)} charts:\n")

    for name in generated:
        path = paths[name]
        file_exists = os.path.exists(path)
        status = "✅" if file_exists else "❌"
        print(f"  {status} {name}")
        print(f"      {path}")

    if skipped:
        print(f"\nSkipped {len(skipped)} charts:\n")
        for name in skipped:
            print(f"  ⏭  {name}")

    # Verify files exist
    print(f"\n{'='*80}")
    print("FILE VERIFICATION")
    print(f"{'='*80}\n")

    for name, path in paths.items():
        if path and os.path.exists(path):
            size = os.path.getsize(path)
            print(f"✅ {path} ({size:,} bytes)")

    return 0 if generated else 1


if __name__ == "__main__":
    sys.exit(main())
