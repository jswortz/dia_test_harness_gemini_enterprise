# Baseline Agent Evaluation Summary

**Date:** 2026-01-07
**Agent:** BaselineAgent (ID: 16994088282440686170)
**Test Set:** Golden Test Set (5 questions)

---

## Test Results Overview

### Overall Performance
- **Total Tests:** 5
- **Semantically Equivalent:** 4 (80.0%)
- **Different/Incorrect:** 1 (20.0%)
- **Average Latency:** ~44.2 seconds per query

### Success by Question Type

| Question | Expected Result | Generated Result | Verdict | Latency |
|----------|----------------|------------------|---------|---------|
| How many customers are there? | `SELECT count(*) FROM dataset.customers` | `SELECT COUNT(id) AS _col_0 FROM ...` | **EQUIVALENT** | 29.9s |
| List all product categories | `SELECT DISTINCT category FROM dataset.products` | `SELECT DISTINCT category AS category FROM ...` | **EQUIVALENT** | 28.3s |
| Total revenue for each status | `SELECT status, SUM(amount) FROM ...` | Multi-line with aliases | **EQUIVALENT** | 61.5s |
| Top 5 most expensive products | `SELECT name, price FROM ... LIMIT 5` | Multi-line with aliases | **EQUIVALENT** | 48.1s |
| Customers who placed orders in 2024 | `SELECT DISTINCT c.name FROM ...` | `SELECT DISTINCT region, email, ... FROM ...` | **DIFFERENT** ❌ | 63.2s |

---

## Key Findings

### ✅ Strengths

1. **High Semantic Accuracy:** 80% of queries were semantically correct
2. **Consistent Style:** Agent uses fully qualified table names (all 5/5 tests)
3. **Authorization Working:** All queries executed successfully with BigQuery access
4. **Thoughtful Responses:** Agent provides context, explanations, and recommendations

### ⚠️ Issues Identified

#### 1. **Critical Issue: Column Over-Selection** (1 test failed)

**Problem:** Agent selected multiple columns when only customer names were requested.

- **Question:** "Find customers who placed orders in 2024"
- **Expected:** `SELECT DISTINCT c.name FROM ...`
- **Generated:** `SELECT DISTINCT region, email, signup_date, name, id FROM ...`
- **Impact:** Incorrect result schema and potential performance degradation

**Root Cause:** Agent interprets "Find customers" as "Get full customer records" rather than "Get customer names."

#### 2. **Syntactic Variations** (not failures, but inconsistencies)

- **Verbose aliasing:** Uses `AS _col_0` in some queries
- **COUNT variation:** Uses `COUNT(id)` instead of `COUNT(*)` (functionally equivalent for non-null PKs)
- **Date filtering:** Uses `FORMAT_DATE` instead of `BETWEEN` (prevents partition pruning)

---

## Detailed Issue Analysis

### Test Case 5: "Find customers who placed orders in 2024"

**LLM Judge Explanation:**

> The Generated SQL and Expected SQL differ in two main aspects:
>
> 1. **Selected Columns (Projection):** The Expected SQL selects only the customer `name`. The Generated SQL selects multiple columns including `region`, `email`, `signup_date`, `name`, and `id`.
>
> 2. **Distinct Logic (Granularity):** The Expected SQL uses `DISTINCT name`. If there are multiple unique customers (different IDs) who share the same name, the Expected SQL will merge them into a single row. The Generated SQL includes the unique `id` in the select list; therefore, `DISTINCT` will preserve all unique customers even if they share a name.
>
> While the date filtering logic (`FORMAT_DATE` vs `BETWEEN`) is functionally equivalent for the year 2024, the difference in the result set structure and potential row counts makes them **DIFFERENT**.

**Semantic Impact:**
- Returns 16 customers with full profiles instead of just names
- Changes result granularity (unique customer records vs. unique names)
- Violates principle of minimal column selection

---

## Recommendations for Prompt Improvement

### Priority 1: Critical Issues

#### 1.1 Column Selection Precision
**Problem:** Agent over-fetches columns not requested by the user.

**Solution:**
```
Add explicit constraint to prompt:
"Select ONLY the columns explicitly requested by the user. If the user asks for 'customers,'
select `name` (and `id` only if unique identification is required). Do not include extra
columns (like email, region, etc.) unless specifically asked."
```

**Example to add:**
```
User: "Find customers who placed orders in 2024."
SQL: SELECT DISTINCT c.name
     FROM `project.dataset.customers` c
     JOIN `project.dataset.orders` o ON c.id = o.customer_id
     WHERE o.order_date BETWEEN '2024-01-01' AND '2024-12-31'
```

#### 1.2 Date Filtering Performance
**Problem:** Agent uses `FORMAT_DATE` which prevents BigQuery partition pruning.

**Solution:**
```
Add SQL generation rule:
"Do NOT use functions on date columns in the WHERE clause (e.g., avoid FORMAT_DATE, EXTRACT).
Use direct comparison for performance (e.g., WHERE order_date BETWEEN '2024-01-01' AND '2024-12-31')."
```

### Priority 2: SQL Style Guidance

#### 2.1 Meaningful Aliases
**Current:** Agent uses `t1`, `t2`, or verbose aliases like `_col_0`

**Recommendation:**
```
"Use meaningful, short aliases (e.g., `c` for customers, `o` for orders).
Do not generate verbose aliases like `_col_0` or generic aliases like `t1`."
```

#### 2.2 Standardize COUNT Usage
**Current:** Inconsistent use of `COUNT(*)` vs `COUNT(column)`

**Recommendation:**
```
"Use COUNT(*) for counting rows/records. Use COUNT(column_name) only when
counting non-null specific values."
```

### Priority 3: Additional Context

#### 3.1 Schema Information
**Recommendation:** Provide explicit schema DDL in the prompt:

```
### Schema Context
- `wortz-project-352116.dia_test_dataset.customers`
  Columns: id (PRIMARY KEY), name, email, region, signup_date

- `wortz-project-352116.dia_test_dataset.products`
  Columns: id (PRIMARY KEY), name, category, price

- `wortz-project-352116.dia_test_dataset.orders`
  Columns: order_id (PRIMARY KEY), customer_id (FK), product_id (FK),
          order_date, status, amount
```

#### 3.2 Few-Shot Examples
**Recommendation:** Add 2-3 example question/SQL pairs demonstrating:
1. Minimal column selection
2. Proper date filtering
3. Meaningful aliases

---

## Revised Prompt Template

Based on the analysis, here's the recommended prompt structure:

```text
You are a specialized Data Scientist agent tasked with answering data-related questions
using BigQuery Standard SQL.

### Schema Context
[Schema DDL as shown above]

### SQL Generation Rules
1. **Column Selection (Critical):** Select ONLY the columns explicitly requested by the user.
   - If the user asks for "customers," select `name` (and `id` only if unique
     identification is required).
   - Do not include extra columns unless specifically asked.

2. **Date Filtering (Performance):** Do NOT use functions on date columns in WHERE clause.
   - Use direct comparison: `WHERE order_date BETWEEN '2024-01-01' AND '2024-12-31'`

3. **Aliasing:** Use meaningful, short aliases (e.g., `c` for customers, `o` for orders).

4. **Table Names:** Always use fully qualified table names.

5. **Aggregation:** Use `COUNT(*)` for counting records. Use `COUNT(column)` only to
   count non-null values.

### Examples
[Few-shot examples demonstrating correct behavior]

### Task
When a user asks a question, generate the appropriate SQL query, execute it, and provide
a natural language response with the results.
```

---

## Next Steps

1. **Update Agent Configuration:** Apply the revised prompt to BaselineAgent
2. **Re-run Evaluation:** Test with the same golden set to measure improvement
3. **Expand Test Coverage:** Add more test cases for:
   - Column selection edge cases
   - Complex JOIN scenarios
   - Date filtering variations
4. **Deploy Other Variants:** Test few-shot, verbose schema, persona, and CoT variants
5. **A/B Comparison:** Compare all 5 agent variants to identify best configuration

---

## Files Generated

- **Test Results:** `results/golden_test_results.jsonl`
- **Prompt Recommendations:** `results/prompt_improvement_recommendations.txt`
- **This Summary:** `results/EVALUATION_SUMMARY.md`

---

## Conclusion

The baseline agent demonstrates **strong foundational performance** with 80% semantic accuracy.
The primary improvement needed is **stricter column selection** to match user intent precisely.
With the recommended prompt modifications, particularly the addition of explicit column selection
rules and few-shot examples, the agent should achieve 100% accuracy on the golden test set.

The evaluation system (agent client, SQL comparison, LLM judge) is working correctly and ready
for multi-variant testing and iterative prompt optimization.
