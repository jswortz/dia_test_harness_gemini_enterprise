"""
Iterative optimization module for single-agent prompt refinement.

This module provides components for closed-loop optimization of Data Insights Agents:
- TrajectoryTracker: Manages iteration history
- SingleAgentDeployer: Deploys and updates agents via PATCH API
- SingleAgentEvaluator: Wraps evaluation with metrics calculation
- PromptImprover: AI-driven prompt refinement suggestions
- IterativeOptimizer: Main loop orchestrator
"""

from .tracker import TrajectoryTracker
from .deployer import SingleAgentDeployer
from .evaluator import SingleAgentEvaluator
from .prompt_improver import PromptImprover
from .optimizer import IterativeOptimizer

__all__ = [
    'TrajectoryTracker',
    'SingleAgentDeployer',
    'SingleAgentEvaluator',
    'PromptImprover',
    'IterativeOptimizer'
]
