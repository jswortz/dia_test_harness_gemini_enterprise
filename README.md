# Data Insights Agent (DIA) Testing Harness

A comprehensive test harness for deploying, verifying, and benchmarking Google Cloud Data Insights Agents (DIA) in parallel. This tool allows you to validate agent configurations, test data routing, and measure performance using golden datasets.

## Features

- **Iterative Optimization (New!)**: Closed-loop prompt refinement with AI-driven suggestions, user approval, and PATCH-based updates.
- **Multi-Variant Deployment**: Deploys 5 distinct agent configurations in parallel (Baseline, Few-Shot, Verbose Schema, Persona, Chain-of-Thought).
- **CSV/Excel Support**: Golden sets can be JSON, CSV, or Excel files with auto-generated metadata.
- **Dynamic Authorization**: Automatically creates and links Authorization Resources with specific OAuth scopes and BigQuery access.
- **Robust Configuration**: Uses "Delete-and-Recreate" strategy to ensure clean state and correct authorization for every deployment.
- **Data Generation**: Scripts to generate synthetic E-commerce datasets (Customers, Products, Orders) and Golden Test Sets.
- **Rich Trajectory Tracking**: Full iteration history with accuracy progression, failure analysis, and prompt change tracking.
- **Reporting**: Automatic results capture in `results.json` (currently pending API connectivity for automated probing).

## Prerequisites

- Python 3.9+
- `uv` (recommended build tool) or `pip`
- Google Cloud Project with Discovery Engine API enabled
- `gcloud` CLI authenticated

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd dia_test_harness_gemini_enterprise
   ```

2. **Initialize Environment**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   GOOGLE_CLOUD_PROJECT=your-project-id
   DIA_LOCATION=global
   DIA_ENGINE_ID=your-engine-id
   BQ_DATASET_ID=dia_test_dataset
   OAUTH_CLIENT_ID=your-oauth-client-id
   OAUTH_SECRET=your-oauth-client-secret
   ```

## Usage

### 1. Generate Data in BigQuery

Load synthetic data into your BigQuery dataset:
```bash
python scripts/load_to_bq.py
```

### 2. Deploy Agents (Multi-Variant)

The harness is configured to deploy 5 parallel agent variants defined in `configs/multi_variant.json`.

**Variants:**
1.  `baseline`: Standard prompt.
2.  `few_shot_context`: Included Q&A examples.
3.  `verbose_schema`: Detailed schema description.
4.  `persona_business`: BI Analyst persona.
5.  `cot_reasoning`: Chain-of-Thought instructions.

**Run Deployment:**
```bash
python scripts/deploy_data_agent.py
```
> **Note**: This script will automatically **delete** any existing agents with the same display names (`Data Agent - <variant>`) before creating new ones. This ensures the latest Authorization keys and configurations are applied.

### 3. Agent Authorization (Required)

Before running automated tests, each agent needs OAuth authorization to access BigQuery:

```bash
# Generate authorization URL for your agent
python scripts/authorize_agent.py
```

This script will:
1. Query the agent to trigger authorization requirements
2. Display the OAuth authorization URL
3. Save the URL to `results/authorization_1.txt`
4. Provide step-by-step authorization instructions

**Authorization Steps:**
1. Copy the displayed URL
2. Open it in your browser
3. Sign in with your Google account
4. Grant BigQuery access permissions
5. You'll be redirected to a confirmation page
6. Authorization is complete - you can now run tests

**Note**: Authorization is required once per agent and persists across queries.

### 4. Run Evaluations

After authorizing your agent:

```bash
# Test with a single question (debug mode)
python scripts/test_evaluation.py

# Run full golden set evaluation
python scripts/run_golden_test.py
```

### 5. Iterative Optimization (New!)

The harness now includes a **closed-loop iterative optimization** mode that automatically refines agent prompts based on evaluation results.

**Workflow:**
1. Deploy a single baseline agent
2. Run evaluation against golden set
3. Analyze failures with AI (Gemini)
4. Suggest prompt improvements
5. User approves/edits suggestions
6. PATCH agent with updated prompt (preserves OAuth)
7. Repeat until accuracy reaches 100% or user stops

**Run Optimization:**
```bash
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --max-iterations 10
```

**Features:**
- **Single Agent Focus**: Deploys and optimizes one "baseline" agent
- **CSV/Excel Support**: Golden sets can be JSON, CSV, or Excel files
  - CSV format: Just two columns: `nl_question`, `expected_sql`
  - Auto-generates UUIDs, complexity analysis, and SQL patterns
- **AI-Driven Suggestions**: Gemini analyzes failures and suggests specific prompt improvements
- **User Approval**: Review and edit AI suggestions before applying
- **PATCH Updates**: Updates agent without delete-recreate (preserves OAuth authorization)
- **Rich Trajectory Tracking**: Full history saved to `results/trajectory_history.json`
  - Iteration-by-iteration comparison
  - Accuracy progression
  - Failure pattern analysis
  - Prompt change descriptions

**Example CSV Golden Set:**
```csv
nl_question,expected_sql
How many customers are there?,SELECT count(*) FROM `dia_test_dataset.customers`
What are the distinct product categories?,SELECT DISTINCT category FROM `dia_test_dataset.products`
```

**Trajectory History Example:**
```json
{
  "agent_name": "baseline",
  "start_time": "2026-01-07T10:00:00",
  "iterations": [
    {
      "iteration": 1,
      "timestamp": "2026-01-07T10:05:23",
      "config": {...},
      "metrics": {
        "total": 5,
        "exact_match": 2,
        "semantically_equivalent": 2,
        "failures": 1,
        "accuracy": 80.0
      },
      "failures": [...],
      "prompt_changes": "Initial configuration"
    },
    {
      "iteration": 2,
      "metrics": {
        "accuracy": 100.0
      },
      "prompt_changes": "Added instruction to select only requested columns"
    }
  ]
}
```

**Iteration Display:**
Each iteration shows:
- Accuracy metrics (exact match, semantic equivalence, failures)
- Comparison to previous iteration (accuracy delta, resolved issues, new failures)
- Detailed failure breakdown
- AI-generated prompt improvement suggestions
- Side-by-side diff of old vs. new prompt

**User Interaction:**
After each iteration, you can:
- **[a] Approve**: Use AI-suggested prompt as-is
- **[e] Edit**: Manually refine the suggested prompt
- **[s] Skip**: Keep current prompt, no changes
- **Continue?**: Choose to run another iteration or stop

### 6. Manual Verification (Alternative)

You can also test agents manually via the Google Cloud Console:

1.  Go to the [Google Cloud Console > Agent Builder](https://console.cloud.google.com/gen-app-builder/engines).
2.  Select your Engine (`DIA_ENGINE_ID`).
3.  Navigate to **Agents**.
4.  You will see 5 agents corresponding to the deployed variants.
5.  Test each agent manually in the Console's "Preview" pane to verify it can query BigQuery and answer questions according to its specific persona/configuration.

## Project Structure

```
.
├── configs/                 # Agent configuration JSONs
│   ├── multi_variant.json   # Main 5-variant config
│   ├── baseline_config.json # Single baseline config (for optimization)
│   └── sample_configs.json
├── data/                    # Generated data and golden sets
│   ├── golden_set.json      # Golden set in JSON format
│   └── golden_set.csv       # Golden set in CSV format (example)
├── scripts/                 # Utility and Deployment scripts
│   ├── check_env.py
│   ├── check_lro.py         # Monitor Liquid Operations
│   ├── create_dummy_datastore.py
│   ├── deploy_data_agent.py # Main deployment script
│   ├── generate_data.py
│   ├── generate_golden_set.py
│   ├── inspect_*.py         # Configuration inspection tools
│   ├── load_to_bq.py
│   ├── authorize_agent.py   # OAuth authorization helper
│   ├── run_golden_test.py   # Run golden set evaluation
│   ├── test_evaluation.py   # Test evaluation pipeline
│   └── verify_connectivity.py
├── src/
│   ├── orchestrator/        # Core harness logic
│   ├── evaluation/          # Evaluation and testing components
│   │   ├── runner.py        # Test runner with metrics
│   │   ├── evaluator.py     # SQL comparison and LLM judge
│   │   ├── agent_client.py  # Agent query client
│   │   └── data_loader.py   # Golden set loader (JSON/CSV/Excel)
│   └── iterative/           # Iterative optimization (NEW!)
│       ├── optimizer.py     # Main loop orchestrator
│       ├── deployer.py      # Single agent deployment with PATCH
│       ├── evaluator.py     # Evaluation wrapper
│       ├── tracker.py       # Trajectory history tracking
│       └── prompt_improver.py # AI-driven prompt refinement
├── results/
│   └── trajectory_history.json # Iteration history and metrics
├── results.json             # Test run outputs
├── pyproject.toml           # Project dependencies
└── README.md
```

## Known Issues

- **OAuth Authorization Required**: v1alpha Data Insights Agents require one-time OAuth authorization to access BigQuery. Use `scripts/authorize_agent.py` to generate the authorization URL. After authorization, automated testing works correctly.
- **Search Dominance**: Implicit routing may favor Search over SQL generation for generic queries.
