# Data Insights Agent (DIA) Optimization Harness

Automated optimization tool for Google Cloud Data Insights Agents. Deploy an agent, authorize it once, then iteratively improve its natural language to SQL generation through AI-powered prompt refinement.

## What This Does

1. **Deploy** a Data Insights Agent to Google Cloud
2. **Authorize** the agent (one-time OAuth setup)
3. **Optimize** the agent's prompts automatically through iterative testing and AI-driven improvements

Each optimization iteration:
- Tests the agent against your golden dataset
- Analyzes failures using Gemini AI
- Intelligently determines which configuration fields to improve:
  - **nl2sql_prompt**: Main SQL generation instructions
  - **schema_description**: Database schema details
  - **nl2sql_examples**: Few-shot learning examples
  - **nl2py_prompt**: Python data processing instructions
  - **allowed_tables**: Table access whitelist
  - **blocked_tables**: Table access blacklist
- Updates the agent with improved configuration
- Tracks all configuration changes and accuracy improvements over time

## Prerequisites

- **Python 3.9+**
- **Google Cloud Project** with:
  - Discovery Engine API enabled
  - BigQuery with your data loaded
  - Gemini Enterprise engine created
- **Authentication**: `gcloud` CLI authenticated

## Installation

```bash
# Clone and setup
git clone <repo-url>
cd dia_test_harness_gemini_enterprise

# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -e .
```

## Configuration

Create a `.env` file in the root directory:

```env
GOOGLE_CLOUD_PROJECT=your-project-id
DIA_LOCATION=global
DIA_ENGINE_ID=your-engine-id
BQ_DATASET_ID=your-dataset-id
```

## Quick Start

### Step 1: Deploy Agent (One-Time)

Deploy your Data Insights Agent:

```bash
dia-harness deploy --config-file configs/baseline_config.json
```

**Output:**
```
✓ AGENT DEPLOYED SUCCESSFULLY

Agent Details:
  Agent ID: 6970595320594450988
  Display Name: Data Agent - baseline
  Project: your-project-id
  Engine: your-engine-id

⚠️  IMPORTANT: OAuth Authorization Required (ONE-TIME SETUP)
```

The deploy command will display detailed authorization instructions.

### Step 2: Authorize Agent (One-Time)

**Authorize via Gemini Enterprise UI (Recommended):**

1. Click the console link provided in deploy output
2. Find your agent: "Data Agent - baseline"
3. Click the agent → Click "Test" or "Chat"
4. Send a test query: `"How many customers are there?"`
5. Click the OAuth authorization link in the response
6. Sign in and grant BigQuery access permissions
7. Send the query again to verify it works

**Note**: Authorization persists forever. You only do this once per agent.

### Step 3: Run Optimization

Now you can optimize the agent as many times as you want:

```bash
# Basic optimization (interactive)
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --max-iterations 10

# Fully automated (no manual approval)
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --max-iterations 10 \
  --auto-accept

# With test dataset (detect overfitting)
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --test-set data/test_set.json \
  --max-iterations 10
```

## Optimization Workflow

Each optimization run follows this process:

```
┌─────────────────────────────────────────────────────┐
│ ITERATION N                                         │
├─────────────────────────────────────────────────────┤
│ 1. Evaluate agent against golden set (3x repeats)  │
│    → Questions: 20                                  │
│    → Correct: 15/20 (75% accuracy)                  │
│                                                     │
│ 2. Analyze failures with Gemini AI                 │
│    → 5 failures detected                            │
│    → Pattern: Missing column selection guidance    │
│                                                     │
│ 3. Generate prompt improvements                    │
│    → Suggested change: Add explicit column rules   │
│    → Show side-by-side diff                         │
│                                                     │
│ 4. User approval (or auto-accept)                  │
│    [a] Approve  [e] Edit  [s] Skip                 │
│                                                     │
│ 5. Update agent via PATCH                          │
│    → New configuration deployed                     │
│    → OAuth authorization preserved                  │
└─────────────────────────────────────────────────────┘
         ↓
    Next Iteration (or stop at 100% accuracy)
```

## Optimization Outputs

Every optimization run generates timestamped artifacts in `results/`:

### 1. Trajectory History
**File**: `results/trajectory_history_<timestamp>.json`

Complete record of all iterations with:
- Configuration changes at each step
- Accuracy metrics (exact match, semantic equivalence, failures)
- Full test results for every question
- Train and test dataset metrics (if test set provided)
- Prompt change descriptions

**Example structure:**
```json
{
  "agent_name": "baseline",
  "start_time": "2026-01-08T14:30:52",
  "iterations": [
    {
      "iteration": 1,
      "timestamp": "2026-01-08T14:32:15",
      "evaluation": {
        "train": {
          "accuracy": 0.75,
          "correct": 15,
          "total_cases": 20,
          "repeat_measurements": [0.75, 0.80, 0.75],
          "failures": [...]
        }
      },
      "configuration": {...},
      "prompt_changes": "Initial configuration"
    },
    {
      "iteration": 2,
      "evaluation": {
        "train": {
          "accuracy": 0.90,
          "correct": 18,
          "total_cases": 20
        }
      },
      "prompt_changes": "Added explicit column selection rules"
    }
  ]
}
```

### 2. Evaluation Results
**Files**: `results/eval_train_<timestamp>.jsonl`, `results/eval_test_<timestamp>.jsonl`

Line-delimited JSON with detailed results for each test question:

```json
{
  "question": "How many customers are there?",
  "expected_sql": "SELECT COUNT(*) FROM customers",
  "generated_sql": "SELECT COUNT(*) FROM customers",
  "exact_match": true,
  "semantically_equivalent": true,
  "error": null,
  "response": "There are 1,234 customers in the database.",
  "thoughts": "I need to count all rows in the customers table..."
}
```

Individual repeat measurements saved as: `eval_train_<timestamp>.jsonl.repeat1`, `.repeat2`, etc.

### 3. Visualization Charts
**Directory**: `results/charts/`

Six automatically generated charts (PNG format):

1. **Accuracy Over Time** - Line chart with error bars showing progression
2. **Accuracy Distribution** - Box plots comparing iterations
3. **Metric Breakdown** - Stacked bars (exact match, semantic, failures)
4. **Question Heatmap** - Pass/fail grid across iterations and questions
5. **Improvement Deltas** - Bar chart of iteration-to-iteration changes
6. **Train vs Test** - Comparison to detect overfitting (if test set provided)

### 4. Comprehensive Report
**File**: `results/OPTIMIZATION_REPORT_<timestamp>.md`

Auto-generated markdown report with:

**Executive Summary:**
- Initial vs final accuracy with improvement percentage
- Number of iterations completed
- ASCII progress chart

**Visualizations:**
- All 6 charts embedded as images

**Iteration Details:**
- Per-iteration breakdown with:
  - Training accuracy (with repeat measurements if N > 1)
  - Test accuracy (if test set provided)
  - Failed questions and error patterns
  - **All configuration fields** with their current values:
    - nl2sql_prompt (with preview and character count)
    - schema_description (character count)
    - nl2sql_examples (number of examples)
    - nl2py_prompt (set/not set)
    - allowed_tables (whitelist count)
    - blocked_tables (blacklist count)
  - Description of configuration changes applied

**Configuration Evolution Table:**
- Comprehensive table tracking ALL config fields across iterations:
  - Train/Test accuracy progression
  - Prompt length evolution
  - Schema description length evolution
  - Number of examples added/removed
  - Python prompt status
  - Table access control changes

**Recommendations:**
- Performance assessment (strong/moderate/poor)
- Overfitting detection warnings
- Improvement trend analysis
- Specific failure categories to address

**Reproduction Commands:**
- How to re-run the optimization
- Analysis commands for inspecting results

### 5. Run ID and Timestamping

Each run displays a unique Run ID at the start:

```
Run ID: 20260108_143052
```

All files from the same run share this timestamp:
- `trajectory_history_20260108_143052.json`
- `eval_train_20260108_143052.jsonl`
- `OPTIMIZATION_REPORT_20260108_143052.md`

This makes it easy to identify and organize related artifacts across multiple optimization runs.

## CLI Commands

### `dia-harness deploy`

Deploy a new Data Insights Agent.

```bash
dia-harness deploy --config-file configs/baseline_config.json
```

**When to use**: One-time setup when creating a new agent.

**Output**: Agent ID, display name, and OAuth authorization instructions.

### `dia-harness optimize`

Run iterative optimization on an existing deployed agent.

```bash
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  [options]
```

**When to use**: Anytime after deploying and authorizing an agent. Run as many times as needed.

**Required**:
- `--config-file`: Agent configuration JSON
- `--golden-set`: Test dataset (JSON, CSV, or Excel)

**Optional flags**:
- `--max-iterations N`: Stop after N iterations (default: 10)
- `--num-repeats N`: Test each iteration N times for statistical reliability (default: 3)
- `--test-set PATH`: Held-out test set for overfitting detection
- `--auto-accept`: Skip manual approval, auto-apply all AI suggestions

## Configuration File

The agent configuration (`configs/baseline_config.json`) includes:

**Important: `display_name` below will be used to match between the `deploy` and `optimize` methods below**

```json
{
  "name": "baseline",
  "display_name": "Data Agent - Baseline",
  "description": "Baseline Data Insights Agent for NL2SQL",

  "nl2sql_prompt": "You are an expert SQL assistant...",
  "schema_description": "The dataset contains e-commerce data...",
  "nl2sql_examples": [
    {
      "query": "How many customers?",
      "expected_sql": "SELECT COUNT(*) FROM customers",
      "expected_response": "There are X customers."
    }
  ],

  "bq_project_id": "${GOOGLE_CLOUD_PROJECT}",
  "bq_dataset_id": "${BQ_DATASET_ID}",

  "allowed_tables": [],
  "blocked_tables": []
}
```

**All fields analyzed and optimized by AI**:
- `nl2sql_prompt`: Main SQL generation instructions (highest priority)
- `schema_description`: Database schema, tables, and column descriptions (high priority)
- `nl2sql_examples`: Few-shot examples showing query patterns (medium priority)
- `nl2py_prompt`: Python data processing instructions (low priority, only if Python processing needed)
- `allowed_tables`: Whitelist of tables the agent can access (medium priority)
- `blocked_tables`: Blacklist of tables to prevent access (medium priority)

The optimizer uses AI to determine which fields need improvement based on failure analysis, then applies changes intelligently with priority-based recommendations.

## Golden Set Format

Your test dataset can be JSON, CSV, or Excel format.

**CSV example** (`data/golden_set.csv`):
```csv
nl_question,expected_sql
How many customers are there?,SELECT COUNT(*) FROM `project.dataset.customers`
What are the top 5 products?,SELECT * FROM `project.dataset.products` ORDER BY sales DESC LIMIT 5
List all orders from 2024,SELECT * FROM `project.dataset.orders` WHERE EXTRACT(YEAR FROM order_date) = 2024
```

**JSON example** (`data/golden_set.json`):
```json
[
  {
    "nl_question": "How many customers are there?",
    "expected_sql": "SELECT COUNT(*) FROM `project.dataset.customers`"
  },
  {
    "nl_question": "What are the top 5 products?",
    "expected_sql": "SELECT * FROM `project.dataset.products` ORDER BY sales DESC LIMIT 5"
  }
]
```

## Project Structure

```
dia_test_harness_gemini_enterprise/
├── configs/
│   └── baseline_config.json       # Agent configuration
├── data/
│   ├── golden_set.json            # Test questions and expected SQL
│   └── test_set.csv               # Optional held-out test set
├── src/
│   ├── orchestrator/              # CLI commands (deploy, optimize)
│   ├── iterative/                 # Optimization logic
│   │   ├── optimizer.py           # Main iteration loop
│   │   ├── deployer.py            # Agent deployment
│   │   ├── evaluator.py           # Test execution
│   │   ├── tracker.py             # History tracking
│   │   ├── prompt_improver.py     # AI-driven improvements
│   │   ├── visualizer.py          # Chart generation
│   │   └── report_generator.py    # Markdown reports
│   └── evaluation/                # Evaluation engine
│       ├── runner.py              # Test runner
│       ├── agent_client.py        # API client
│       ├── evaluator.py           # SQL comparison
│       └── data_loader.py         # Dataset loading
├── scripts/
│   ├── data/                      # Data generation utilities
│   ├── deployment/                # Deployment scripts
│   └── utils/                     # Environment checkers
├── results/                       # Generated outputs
│   ├── trajectory_history_*.json
│   ├── eval_train_*.jsonl
│   ├── OPTIMIZATION_REPORT_*.md
│   └── charts/*.png
└── .env                           # Environment configuration
```

## Tips for Best Results

1. **Start with quality examples**: Your golden set should cover diverse query patterns
2. **Use 3+ repeats**: Statistical reliability improves with repeat measurements
3. **Provide test set**: Detects if improvements overfit to training data
4. **Review AI suggestions**: Even with `--auto-accept`, check the generated reports
5. **Iterate multiple times**: Run optimization multiple times with different starting configs

## Troubleshooting

**"Agent Not Found" error:**
- Make sure you ran `dia-harness deploy` first
- Check that the config file `name` matches between deploy and optimize

**OAuth authorization errors:**
- Complete the OAuth flow via Gemini Enterprise UI
- Authorization is required once per agent, then persists

**Low accuracy:**
- Review failures in the evaluation JSONL files
- Check if your `schema_description` includes all relevant tables/columns
- Add more `nl2sql_examples` for common query patterns

**Import errors:**
- Ensure you're in the virtual environment: `source .venv/bin/activate`
- Reinstall dependencies: `uv pip install -e .`

## Advanced Usage

### Custom Repeat Measurements
```bash
# Run each test 5 times for high confidence
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --num-repeats 5
```

### Overfitting Detection
```bash
# Evaluate on both train and test sets
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --test-set data/test_set.json
```

### Fully Automated Pipeline
```bash
# No manual intervention required
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --max-iterations 20 \
  --auto-accept
```

