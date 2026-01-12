# Data Insights Agent (DIA) Optimization Harness

Automated optimization tool for Google Cloud Data Insights Agents. Deploy an agent, authorize it once, then iteratively improve its natural language to SQL generation through AI-powered prompt refinement and **research-backed semantic equivalence evaluation**.

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
DIA_AGENT_ID=  # ⚠️ ADD THIS AFTER DEPLOYING (see Step 1 below)
JUDGEMENT_MODEL=gemini-3-flash-preview  # Optional: LLM for SQL semantic comparison (default: gemini-2.5-pro)
USE_FLEXIBLE_SCORING=true  # Enable 100-point SQL rubric (default: true)
```

**Configuration Options:**
- `DIA_AGENT_ID`: Populated after deployment (see Step 1)
- `JUDGEMENT_MODEL`: Gemini model for semantic SQL evaluation
  - `gemini-3-flash-preview` (recommended): Fast, cost-effective, good accuracy
  - `gemini-2.5-pro`: Higher quality but slower and more expensive
  - `gemini-1.5-flash`: Faster alternative
  - Default: `gemini-2.5-pro` if not specified
- `USE_FLEXIBLE_SCORING`: SQL evaluation method (**recommended: `true`**)
  - `true` (default): **100-point flexible rubric** - Recognizes partial correctness across 6 categories
    - **Table Selection** (25 pts): Correct tables identified
    - **Join Logic** (20 pts): Proper table relationships
    - **Filter Accuracy** (20 pts): WHERE clause correctness
    - **Aggregation** (15 pts): GROUP BY, aggregation functions
    - **Column Selection** (10 pts): SELECT clause accuracy
    - **Formatting** (10 pts): Syntax, aliases, readability
  - `false`: Binary pass/fail - Query either matches exactly or is semantically equivalent
  - **Why flexible scoring?** Provides granular feedback for optimization, recognizes incremental improvements, and helps identify specific weaknesses in agent configuration

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

**🚨 CRITICAL STEP - DO THIS NOW:**

**Copy the Agent ID** from the output above and add it to your `.env` file:

```bash
# Add this line to your .env file
echo "DIA_AGENT_ID=6970595320594450988" >> .env
```

**Or manually edit `.env`** to add:
```env
DIA_AGENT_ID=6970595320594450988
```

⚠️ **Without this step, the `optimize` command will not find your agent!**

The deploy command will also display detailed authorization instructions.

### Step 2: Authorize Agent (One-Time)

**Authorize via Gemini Enterprise UI (Recommended):**

1. Go to the console
2. Find your agent
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

## SQL Semantic Equivalence Evaluation

The optimization system uses an **enhanced AI-powered judgement model** to determine if generated SQL is semantically equivalent to expected SQL, even when syntax differs.

### Research-Backed Best Practices (2026)

The judgement model implements state-of-the-art techniques from recent Text-to-SQL research:

**1. Miniature & Mull Prompting**
- LLM executes queries on hypothetical database instances
- Searches for counterexamples where results would differ
- Achieves **100% accuracy** in identifying SQL mistakes (vs. basic prompting)

**2. Schema-Aware Evaluation**
- Automatically includes relevant database schema in judgement context
- Improves F1 scores from 0.70-0.76 to significantly higher
- Validates table and column references against actual schema

**3. Multi-Dimensional Scoring Rubric**
```
Logical Equivalence (0-10)   - Same logical structure?
Result Set Match (0-10)      - Identical results?
Performance Similarity (0-5) - Similar execution characteristics?
────────────────────────────
Total Score: X/25

Score >= 25 → EQUIVALENT
Score < 25  → DIFFERENT
```

**4. Semantic Equivalence Pattern Library**

Recognizes these common SQL transformations that preserve semantics:

| Pattern | Example |
|---------|---------|
| **JOIN variations** | `INNER JOIN` vs `WHERE` clause with table list |
| **Aggregation** | `DISTINCT` vs `GROUP BY` for unique values |
| **Filtering** | `OR` conditions vs `UNION` |
| **Syntax** | Table aliases vs full names, whitespace differences |
| **Date/Time** | `BETWEEN` vs `>= AND <=`, different date formats |
| **Calculations** | Reordered math expressions, equivalent percentages |

**5. Common Error Pattern Recognition**

Automatically detects these failure modes:
- Missing/extra JOIN conditions
- Incorrect aggregation grouping
- Wrong filtering logic (AND vs OR)
- Date range errors
- Missing DISTINCT when needed
- Incorrect column/table references

### Evaluation Metrics

For each test question, the system produces:

**Exact Match** - Character-level comparison (after whitespace normalization)
```sql
✓ Exact:   SELECT COUNT(*) FROM customers
✓ Match:   SELECT   COUNT(*)   FROM   customers
```

**Semantic Equivalence** - AI judgement with detailed analysis
```sql
Expected:  SELECT * FROM orders WHERE status = 'pending' OR status = 'processing'
Generated: SELECT * FROM orders WHERE status IN ('pending', 'processing')

Judgement: EQUIVALENT
Reason:    IN clause is logically equivalent to OR conditions
Score:     25/25 (Logic: 10/10, Results: 10/10, Performance: 5/5)
```

**Failure with Counterexample**
```sql
Expected:  SELECT DISTINCT category FROM products
Generated: SELECT category FROM products

Judgement: DIFFERENT
Reason:    Missing DISTINCT - will return duplicate rows
Score:     15/25 (Logic: 5/10, Results: 5/10, Performance: 5/5)
Counterexample: If products has [Electronics, Electronics, Clothing],
                Expected returns [Electronics, Clothing] (2 rows)
                Generated returns [Electronics, Electronics, Clothing] (3 rows)
```

### Flexible Scoring (100-Point Rubric)

**Default Evaluation Method** - Recognizes partial correctness instead of binary pass/fail:

**Example: Partially Correct Query**
```sql
Expected:  SELECT market_name, SUM(sales)
           FROM sales_data
           INNER JOIN markets ON sales_data.market_id = markets.id
           WHERE date >= '2025-01-01' AND date <= '2025-01-31'
           GROUP BY market_name

Generated: SELECT market_name, SUM(sales)
           FROM sales_data
           INNER JOIN markets ON sales_data.market_id = markets.id
           WHERE date >= '2025-01-01'
           GROUP BY market_name

Flexible Score: 75/100
  ✓ Table Selection: 25/25 (Correct tables)
  ✓ Join Logic: 20/20 (Proper join condition)
  ✗ Filter Accuracy: 10/20 (Missing end date filter)
  ✓ Aggregation: 15/15 (Correct SUM and GROUP BY)
  ✓ Column Selection: 10/10 (Correct columns)
  ✓ Formatting: 5/10 (Good structure, minor style issues)

Binary Score: 0/100 (Would be marked as complete failure)
```

**Why Use Flexible Scoring?**
- **Granular Feedback**: Identifies exactly which parts of SQL generation need improvement
- **Incremental Progress**: Tracks improvements even when query isn't perfect
- **Better Optimization**: AI can focus on specific weaknesses (e.g., "improve filter logic")
- **Realistic Evaluation**: Real-world queries often have minor issues but still provide value

**When to Use Binary Scoring** (`USE_FLEXIBLE_SCORING=false`):
- Production validation where only perfect queries are acceptable
- Compliance scenarios requiring exact SQL matches
- When you want strict pass/fail metrics

### Benefits for Optimization

1. **Reduced False Negatives** - Recognizes valid SQL with different syntax → higher accuracy
2. **Reduced False Positives** - Structured rubrics prevent incorrect equivalence claims
3. **Better Failure Analysis** - Detailed scoring reveals which aspect failed
4. **Targeted Improvements** - Counterexamples provide concrete debugging info
5. **Faster Convergence** - Accurate classification → cleaner optimization signal

### Research Sources

Based on 2026 Text-to-SQL evaluation literature:
- LLM-SQL-Solver: Can LLMs Determine SQL Equivalence? (arXiv 2312.10321v2)
- Text To SQL: Evaluating SQL Generation with LLM as a Judge (Arize AI)
- LLM-as-a-Judge: Practical Guide to Automated Model Evaluation
- Best Practices for Text-to-SQL with Meta Llama 3 (AWS ML Blog)

See `JUDGEMENT_MODEL_IMPROVEMENTS.md` for complete research summary and implementation details.

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

**Important - Agent Identification:**
- **Recommended**: Set `DIA_AGENT_ID` in `.env` after deploying (fast, reliable)
- **Fallback**: If `DIA_AGENT_ID` is not set, the optimizer searches by `display_name`
- The `display_name` must match exactly between deploy and optimize if using fallback method

**All fields analyzed and optimized by AI**:
- `nl2sql_prompt`: Main SQL generation instructions (highest priority)
- `schema_description`: Database schema, tables, and column descriptions (high priority)
  - **Also used by semantic equivalence judge** to validate SQL correctness
  - Improves judgement accuracy by providing table/column context
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
2. **Include comprehensive schema_description**: The semantic equivalence judge uses this to validate SQL - improves accuracy by ~5-10%
3. **Use 3+ repeats**: Statistical reliability improves with repeat measurements
4. **Provide test set**: Detects if improvements overfit to training data
5. **Review AI suggestions**: Even with `--auto-accept`, check the generated reports
6. **Iterate multiple times**: Run optimization multiple times with different starting configs
7. **Trust semantic equivalence**: The judge recognizes valid SQL with different syntax (e.g., `IN` vs `OR`, `BETWEEN` vs `>= AND <=`)

## Troubleshooting

**"Agent Not Found" error:**
- **Most Common**: Did you add `DIA_AGENT_ID` to your `.env` file after deploying? (See Step 1)
- Check your `.env` file has: `DIA_AGENT_ID=your-agent-id-number`
- Alternative: If `DIA_AGENT_ID` is not set, the optimizer searches by `display_name` - ensure it matches between deploy and optimize
- Make sure you ran `dia-harness deploy` first

**OAuth authorization errors:**
- Complete the OAuth flow via Gemini Enterprise UI (see Step 2)
- Authorization is required once per agent, then persists forever
- Test the agent in the UI to verify it can query BigQuery successfully

**Low accuracy:**
- Review failures in the evaluation JSONL files - the semantic judge provides detailed counterexamples
- Check if your `schema_description` includes all relevant tables/columns (used by both agent and judge)
- Add more `nl2sql_examples` for common query patterns
- Ensure your golden set SQL queries use the correct dataset prefix
- Check semantic equivalence judgements - the system may be correctly recognizing valid alternative SQL

**Import errors:**
- Ensure you're in the virtual environment: `source .venv/bin/activate`
- Reinstall dependencies: `uv pip install -e .`

**Missing charts or reports:**
- Charts are generated in `results/charts/` after each optimization run
- If charts are missing, check the console output for visualization errors
- Reports are saved as `results/OPTIMIZATION_REPORT_<timestamp>.md`

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

