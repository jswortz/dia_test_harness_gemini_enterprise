# Agent Optimization Report

**Agent ID:** `6970595320594450988`
**Report Generated:** 2026-01-08 04:56:12
**Total Iterations:** 2
**Framework:** Data Insights Agent (DIA) Test Harness

---


## Executive Summary

### Key Results

| Metric | Initial | Final | Improvement |
|--------|---------|-------|-------------|
| **Train Accuracy** | 80.00% | 60.00% | -20.00% |
| **Test Accuracy** | 80.00% | 60.00% | -20.00% |
| **Iterations** | - | 2 | - |

### Progress Chart

```
Train Accuracy
Max: 80.00%  Min: 60.00%

 80.0% |█ 
 78.0% |█ 
 76.0% |█ 
 74.0% |█ 
 72.0% |█ 
 70.0% |█ 
 68.0% |█ 
 66.0% |█ 
 64.0% |█ 
 62.0% |█ 
       +--
        01
        Iteration
```


## Visualizations



## Iteration Details

### Iteration 0

**Train Metrics:**
- Accuracy: 80.00% (4/5)
- Repeat measurements: 80.00% ± 0.00%

**Test Metrics:**
- Accuracy: 80.00% (4/5)

**Failures:** 3 total

1. **Q:** Show me the top 5 most expensive products
   **Error:** Unknown error
2. **Q:** What's the total revenue by category?
   **Error:** Unknown error
3. **Q:** Show me customer names who made purchases in December 2024
   **Error:** Unknown error

**Configuration Fields:**
- **nl2sql_prompt**: `You are a specialized Data Scientist agent. Your job is to query the BigQuery database to answer user questions.  IMPORTANT GUIDELINES: 1. Generate accurate BigQuery SQL queries. Use only the informat...` (1236 chars)
- **schema_description**: `The dataset contains e-commerce data with the following tables:  1. customers table: Contains customer information    - id (STRING): Unique customer i...` (1242 chars)
- **nl2sql_examples**: 891 examples provided

**Changes Made:** Initial configuration

---

### Iteration 1

**Train Metrics:**
- Accuracy: 60.00% (3/5)
- Repeat measurements: 60.00% ± 28.28%

**Test Metrics:**
- Accuracy: 60.00% (3/5)

**Failures:** 3 total

1. **Q:** Show me the top 5 most expensive products
   **Error:** Unknown error
2. **Q:** What's the total revenue by category?
   **Error:** Unknown error
3. **Q:** Show me customer names who made purchases in December 2024
   **Error:** Unknown error

**Configuration Fields:**
- **nl2sql_prompt**: `You are a specialized Data Scientist agent. Your job is to query the BigQuery database to answer user questions.  IMPORTANT GUIDELINES: 1. Generate accurate BigQuery SQL queries. Use only the informat...` (1741 chars)
- **schema_description**: `The dataset contains e-commerce data with the following tables:  1. customers table: Contains customer information    - id (STRING): Unique customer i...` (1269 chars)
- **nl2sql_examples**: 1313 examples provided

**Changes Made:** nl2sql_prompt: Auto-approved AI-suggested improvements to address failures; schema_description: Failures 2 and 3 show the agent is using tables (`order_items`, `orders`) that are not described in ; nl2sql_examples: Adding an example that shows how to use `SELECT *` with `ORDER BY` and `LIMIT` might improve the age

---



## Configuration Evolution

| Iter | Train | Test | Prompt | Schema | Examples | Py Prompt | Tables |
|------|-------|------|--------|--------|----------|-----------|--------|
| 0 | 80.0% | 80.0% | 1236ch | 1242ch | 891ex | No | All |
| 1 | 60.0% | 60.0% | 1741ch | 1269ch | 1313ex | No | All |

**Legend:**
- Prompt/Schema: Character count
- Examples: Number of few-shot examples (ex)
- Py Prompt: Whether nl2py_prompt is set
- Tables: A=Allowed count, B=Blocked count


## Recommendations

### ❌ Poor Performance

The agent achieved only 60.00% training accuracy. Significant prompt engineering or architectural changes needed.

### 🔧 Address 3 Remaining Failures

Top failure categories to investigate:
- 3x: `Unknown...`



## Appendix

### Raw Data

Complete trajectory history is available in:
- `results/trajectory_history_6970595320594450988.json`
- `results/iteration_*.json` (individual iteration files)

### Reproduction Commands

To reproduce this optimization run:

```bash
# Set up environment
source .venv/bin/activate
export GOOGLE_CLOUD_PROJECT=your-project-id

# Run iterative optimization
python scripts/run_iterative_optimizer.py \
  --agent-id 6970595320594450988 \
  --train-set data/golden_set.json \
  --test-set data/test_set.json \
  --max-iterations 10 \
  --repeat-measurements 3
```

### Analysis Commands

```bash
# View detailed iteration results
cat results/iteration_*.json | jq '.evaluation.train.accuracy'

# Extract all failure cases
cat results/trajectory_history_*.json | jq '.iterations[].evaluation.train.failures'

# Compare configurations
cat results/trajectory_history_*.json | jq '.iterations[].configuration.nl2sql_prompt'
```

---

*Report generated on 2026-01-08 04:56:12*
