# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A comprehensive test harness for deploying, verifying, and benchmarking Google Cloud Data Insights Agents (DIA). The system supports multi-variant agent deployment with different prompt configurations (baseline, few-shot, verbose schema, persona-based, chain-of-thought reasoning) for performance comparison.

## Environment Setup

Required environment variables in `.env`:
```
GOOGLE_CLOUD_PROJECT=your-project-id
DIA_LOCATION=global
DIA_ENGINE_ID=your-engine-id
BQ_DATASET_ID=dia_test_dataset
OAUTH_CLIENT_ID=your-oauth-client-id
OAUTH_SECRET=your-oauth-client-secret
```

Install dependencies:
```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

## Common Commands

### Data Generation and Loading
```bash
# Generate synthetic e-commerce data
python scripts/data/generate_data.py

# Load data into BigQuery
python scripts/data/load_to_bq.py

# Generate golden test set
python scripts/data/generate_golden_set.py
```

### Agent Deployment
```bash
# Deploy all 5 agent variants (uses delete-and-recreate strategy)
python scripts/deployment/deploy_data_agent.py
```

### Testing and Evaluation

**IMPORTANT: OAuth Authorization Required First**

Before running evaluations, agents must be authorized to access BigQuery:

```bash
# Generate OAuth authorization URL for your agent
python scripts/deployment/authorize_agent.py

# This will:
# 1. Query the agent to trigger authorization requirements
# 2. Extract and display the OAuth authorization URL
# 3. Save the URL to results/authorization_1.txt
# 4. Provide step-by-step instructions to authorize

# After visiting the URL and authorizing, proceed with tests:
```

#### Iterative Optimization (Recommended)

**NEW: Two-Step Workflow with Separate Deployment**

**Step 1: First-Time Deployment and Authorization**

```bash
# Deploy the agent (one-time setup)
dia-harness deploy --config-file configs/baseline_config.json

# This will:
# 1. Deploy the agent to Gemini Enterprise
# 2. Display OAuth authorization instructions
# 3. Provide links to authorize via UI or CLI

# After deployment, authorize the agent via Gemini Enterprise UI:
# - Navigate to the provided console link
# - Find your agent in the agents list
# - Test the agent and click the OAuth authorization link
# - Grant BigQuery access permissions
```

**Step 2: Run Optimization (uses existing authorized agent)**

```bash
# Basic optimization with repeat measurements (default: 3)
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --max-iterations 10

# With test dataset (overfitting detection)
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --test-set data/test_set.json \
  --max-iterations 10 \
  --num-repeats 3

# Fully automated (no manual approval)
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --max-iterations 10 \
  --auto-accept
```

**CLI Commands:**
- `dia-harness deploy` - Deploy agent and show OAuth authorization instructions (one-time setup)
- `dia-harness optimize` - Run optimization on existing deployed agent (always)

**CLI Flags (for optimize):**
- `--num-repeats N` - Run each test N times (default: 3) for statistical reliability
- `--test-set PATH` - Optional held-out test set (not used for optimization decisions)
- `--auto-accept` - Automatically approve all AI-suggested improvements
- `--max-iterations N` - Maximum optimization iterations (default: 10)

**Outputs:**
- `results/trajectory_history.json` - Full iteration history with train/test metrics
- `results/charts/*.png` - 6 visualization charts (accuracy trends, distributions, heatmaps, etc.)
- `results/OPTIMIZATION_REPORT.md` - Comprehensive markdown report
- `results/eval_iteration_*.jsonl` - Per-iteration evaluation results

### Timestamped Results

All optimization runs generate timestamped artifacts (format: `YYYYMMDD_HHMMSS`):

**Outputs:**
- `results/trajectory_history_<timestamp>.json` - Full iteration history with train/test metrics
- `results/eval_train_<timestamp>.jsonl` - Training set evaluation results
- `results/eval_test_<timestamp>.jsonl` - Test set evaluation results (if provided)
- `results/eval_train_<timestamp>.jsonl.repeat<N>` - Individual repeat measurements
- `results/OPTIMIZATION_REPORT_<timestamp>.md` - Comprehensive markdown report with charts
- `results/charts/*.png` - 6 visualization charts (accuracy trends, distributions, heatmaps, etc.)

**Run ID**: Displayed at start of optimization, used consistently across all files.

### Data Leakage Prevention

**CRITICAL: The optimization system is designed to NEVER leak test data into improvement decisions.**

The iterative optimizer follows strict data separation principles:

1. **Training Set Usage**:
   - ONLY training set failures and successes are analyzed for improvement feedback
   - AI improvement suggestions (PromptImprover, ConfigFieldAnalyzer) receive ONLY training data
   - All optimization decisions are based on training performance

2. **Test Set Usage**:
   - Test set is evaluated in parallel but kept strictly separate
   - Test metrics are ONLY used for:
     - Display/reporting purposes
     - Overfitting detection warnings
     - Final performance validation
   - Test data is NEVER passed to improvement functions

3. **Implementation Safeguards**:
   - Explicit docstring warnings in all improvement functions
   - Comments marking training-only data flow
   - Validation checks to catch accidental test data usage
   - Clear separation in code between train/test evaluation paths

4. **Files with Safeguards**:
   - `src/iterative/optimizer.py`: Main orchestration with explicit train/test separation
   - `src/iterative/prompt_improver.py`: Training-only prompt improvement
   - `src/iterative/config_analyzer.py`: Training-only config field analysis

**Why This Matters**: Leaking test data into optimization would invalidate test set metrics as an unbiased estimate of generalization performance. The system must optimize on training data only and use test data purely for held-out evaluation.

### OPRO-Aligned Optimization

**NEW**: The iterative optimizer is now aligned with Google DeepMind's **OPRO (Optimization by PROmpting)** research (Yang et al., 2024).

#### Key OPRO Features

1. **Full Trajectory Context**:
   - The AI improver receives ALL past prompts with their accuracy scores (not just the last iteration)
   - Trajectory is sorted in ascending order (worst to best) to leverage recency bias
   - LLMs pay more attention to the end of context, so best prompts are shown last
   - Enables pattern recognition: AI learns which prompt patterns correlate with higher scores

2. **Temperature Tuning**:
   - Default temperature: **1.0** (per OPRO research finding)
   - Balances exploration (trying new approaches) and exploitation (refining what works)
   - Temperature range: 0.0-2.0
     - 0.0-0.5: Conservative, less diverse
     - 1.0: Optimal balance (OPRO finding)
     - 1.5-2.0: Creative but potentially random

3. **Top-N Trajectory Filtering**:
   - Keeps only best N prompts (default: 10) to avoid context overflow
   - Focuses AI on high-performing patterns
   - Configurable via `max_prompt_length` parameter

#### OPRO Research Results

From the paper "Large Language Models as Optimizers":
- **GSM8K**: 71.8% (human baseline) → 80.2% (OPRO-optimized) = +8% improvement
- **BBH Tasks**: 5-50% improvement over baselines
- **Key Finding**: Full trajectory context outperformed single-iteration approaches by 15-20%

#### How It Works

```python
# Each optimization iteration:
1. Fetch top-10 best prompts from history (sorted worst → best)
2. Build meta-prompt showing:
   - All 10 past prompts with their accuracy scores
   - Current failures and successes
   - Goal: "Generate a prompt better than X% (current best)"
3. AI generates improved prompt using temperature=1.0
4. Evaluate, add to trajectory, repeat
```

#### Configuration

The optimizer automatically uses OPRO approach when trajectory history exists:

```python
# In optimizer.py:
trajectory_history = tracker.get_top_n_by_accuracy(n=10)

# In prompt_improver.py:
improver = PromptImprover(
    project_id=project_id,
    location=location,
    temperature=1.0  # OPRO optimal setting
)
```

**Benefits over single-iteration approach**:
- ✅ Learns from full optimization history
- ✅ Avoids repeating past mistakes
- ✅ Identifies high-scoring prompt patterns
- ✅ Faster convergence (fewer iterations to target accuracy)
- ✅ Better final performance (+5-10% accuracy expected)

#### Traditional Evaluation

```bash
# Run the test harness CLI (orchestrator - multi-variant)
dia-harness run-all --config-file configs/multi_variant.json --golden-set data/golden_set.json --use-real-api
```

### Utility Scripts

Located in `scripts/utils/`:

```bash
# Check environment variables
python scripts/utils/check_env.py

# Check Long-Running Operations (LRO) status
python scripts/utils/check_lro.py
```

**Note**: Debug and inspection scripts have been removed in favor of CLI commands.

## Architecture

### Two-Layer Client Abstraction

The harness has two parallel agent client implementations:

1. **Orchestrator Layer** (`src/orchestrator/`):
   - `agent_client.py`: Contains `MockAgentClient` and `RealAgentClient`
   - `RealAgentClient` uses a persistent engine approach - patches existing agent configs rather than creating/deleting agents
   - Uses v1alpha API for agent configuration and v1beta for querying
   - Implements `@mention` routing for multi-agent selection

2. **Evaluation Layer** (`src/evaluation/`):
   - `agent_client.py`: Separate implementation for golden set evaluation
   - `runner.py`: TestRunner executes golden set tests with two-phase querying (initial question + "what was the sql used" follow-up)
   - `evaluator.py`: SQLComparator for exact matching and JudgementModel for semantic equivalence via Gemini

### Multi-Variant Configuration System

Agent variants are defined in `configs/multi_variant.json` with fields:
- `name`: Variant identifier (baseline, few_shot_context, verbose_schema, persona_business, cot_reasoning)
- `nl2sql_prompt`: Base prompt template
- `params`: Additional context (examples, schema_context)
- `data_store_ids`: Associated datastores

### Comprehensive Baseline Configuration

**NEW:** `configs/baseline_config.json` now includes ALL available API fields:

```json
{
  "name": "baseline",
  "description": "Comprehensive baseline with all API fields",
  "display_name": "Data Agent - Baseline",
  "icon_uri": null,
  "tool_description": "Use this agent to query BigQuery data...",

  "nl2sql_prompt": "You are a specialized Data Scientist agent...",
  "nl2py_prompt": null,

  "schema_description": "The dataset contains e-commerce data with...",

  "nl2sql_examples": [
    {
      "query": "How many customers are there?",
      "expected_sql": "SELECT COUNT(*) FROM `dataset.customers`",
      "expected_response": "There are X customers in the database."
    }
  ],

  "allowed_tables": [],
  "blocked_tables": [],

  "bq_project_id": "${GOOGLE_CLOUD_PROJECT}",
  "bq_dataset_id": "${BQ_DATASET_ID}"
}
```

**Benefits:**
- Schema description helps agent understand table relationships
- Few-shot examples provide concrete patterns
- Table access control for security
- Complete configuration enables better optimization

### Delete-and-Recreate Deployment Strategy

The deployment script (`scripts/deploy_data_agent.py`) deliberately deletes existing agents before creating new ones to ensure:
1. Fresh OAuth authorization resources are linked
2. Latest configurations are applied without state conflicts
3. Clean deployment state for testing

This is NOT a bug - it's intentional behavior documented in README.md.

### API Version Split

- **v1alpha**: Agent creation, patching, deployment, authorization, **and querying via streamAssist**
- **v1beta**: Session creation, answer queries via servingConfs (used in orchestrator layer)
- The harness navigates this split by using appropriate endpoints for each operation

### Critical: agentsSpec Parameter for Querying

When querying Data Insights Agents via the evaluation layer:

**MUST include `agentsSpec` in the request:**
```json
{
  "session": "projects/.../sessions/-",
  "query": {"text": "Your question"},
  "agentsSpec": {
    "agentSpecs": [{"agentId": "your-agent-id"}]
  }
}
```

**Without `agentsSpec`**: The query goes to the default assistant, NOT the Data Insights Agent. You will not get BigQuery access or agent-specific behavior.

The evaluation agent client (`src/evaluation/agent_client.py`) correctly implements this by always including `agentsSpec` with the agent ID in every query.

### Session-Based Follow-Up Pattern

When testing agent SQL generation:
1. Send initial natural language question → captures session ID from response
2. Follow up with "what was the sql query used for the previous answer?" using the session ID
3. Parse SQL from either initial response or follow-up response

This pattern is implemented in `src/evaluation/runner.py:run()`.

### SQL Extraction and Comparison

`TestRunner.parse_response()` extracts:
- `thoughts`: Internal reasoning (marked with thought=True in grounded content)
- `response`: Natural language answer to user
- `generated_sql`: Extracted from markdown code blocks or bare SELECT statements

Comparison flow:
1. Exact match via `SQLComparator` (normalized whitespace)
2. If mismatch, invoke `JudgementModel` (Gemini) for semantic equivalence explanation

## Key Constraints

### OAuth Authorization Requirement

Data Insights Agents require OAuth authorization to access BigQuery:

1. **First-time setup**: Each agent requires user to visit an OAuth authorization URL
2. **Authorization flow**:
   - Agent receives query requiring BigQuery access
   - Agent returns `requiredAuthorizations` in response with authorization URI
   - User visits URI, signs in, grants BigQuery permissions
   - Subsequent queries execute normally and return SQL results
3. **Script helper**: `scripts/authorize_agent.py` automates extraction and display of authorization URLs
4. **One-time per agent**: Authorization persists for the agent, not needed for every query

**Without authorization**: Agents can receive queries via `agentsSpec` and route correctly, but cannot execute BigQuery queries. Responses will contain authorization requirements instead of SQL results.

### v1alpha API Limitations

The evaluation layer uses v1alpha `streamAssist` endpoint which requires OAuth authorization (see above). The orchestrator layer uses v1beta endpoints which have different authentication flows.

### Persistent vs. Ephemeral Agents

The `RealAgentClient` in orchestrator assumes a persistent engine with a default agent that gets patched. This differs from creating/deleting ephemeral agents. The `create_agent()` method returns the engine_id, not a unique agent ID.

## Testing with Real vs Mock APIs

The CLI supports `--use-real-api` flag:
- Without flag: Uses `MockAgentClient` (simulated responses, no external calls)
- With flag: Uses `RealAgentClient` (requires valid GCP credentials and resources)

Mock client provides deterministic responses based on question keywords (count, list) for harness logic validation.

## Important Files

### Configuration
- `configs/baseline_config.json`: **NEW** Comprehensive baseline with ALL API fields
- `configs/multi_variant.json`: 5 agent configurations for parallel testing

### Iterative Optimization (NEW)
- `src/iterative/optimizer.py`: Main orchestration loop with repeat measurements, test datasets, auto-accept
- `src/iterative/evaluator.py`: Evaluation with repeat measurement aggregation
- `src/iterative/deployer.py`: Agent deployment with comprehensive field support
- `src/iterative/tracker.py`: Trajectory tracking with train/test metrics
- `src/iterative/prompt_improver.py`: AI-driven prompt refinement with auto-accept
- `src/iterative/config_analyzer.py`: **NEW** AI analysis of which config fields to improve
- `src/iterative/visualizer.py`: **NEW** Chart generation (6 chart types)
- `src/iterative/report_generator.py`: **NEW** Comprehensive markdown reports

### Orchestrator & CLI
- `src/orchestrator/main.py`: CLI entry point (`dia-harness` command) with new flags
- `src/orchestrator/engine.py`: TestEngine orchestrates parallel config evaluation
- `src/orchestrator/agent_client.py`: Agent deployment and querying (persistent engine model)

### Evaluation
- `src/evaluation/runner.py`: Golden set test execution with session follow-up
- `src/evaluation/evaluator.py`: SQL comparison and LLM-based judgement
- `src/evaluation/agent_client.py`: Agent query client with `agentsSpec` routing

### Scripts
- `scripts/deploy_data_agent.py`: Multi-variant deployment with OAuth authorization
- `scripts/authorize_agent.py`: **OAuth authorization URL generator** - run this first before evaluations
- `scripts/test_evaluation.py`: Full evaluation pipeline test with single test case
- `scripts/run_golden_test.py`: Execute full golden set evaluation

## Documentation References

The `.agent/rules/` directory contains references to external documentation:
- Data Insights Agent API: https://docs.cloud.google.com/gemini/enterprise/docs/data-agent
- Gemini Enterprise API reference: https://docs.cloud.google.com/generative-ai-app-builder/docs/reference/rest

Consult these when working with API calls or authentication flows.
