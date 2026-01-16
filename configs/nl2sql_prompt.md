# NL2SQL Prompt

This file contains the system prompt used by the agent to convert natural language queries to SQL.

## Purpose

This prompt guides the agent's behavior when translating user questions into BigQuery SQL queries. It should include:

- Instructions on SQL generation style and best practices
- Query type classification rules (e.g., named groups, single markets, ranking, comp sales)
- KPI definitions and canonical formulas
- SQL templates for common query patterns
- Syntax and style requirements
- Critical rules and guardrails (e.g., division safety, rounding conventions)

## Usage

This file is read by `scripts/populate_config_from_markdown.py` and its contents are used to populate the `nl2sql_prompt` field in `configs/baseline_config.json`.

## How to Edit

1. Write or update your complete NL2SQL system prompt in this markdown file
2. Run: `python scripts/populate_config_from_markdown.py`
3. The script will automatically update `baseline_config.json` with the new prompt

## Example Structure

```
You are a Senior Data Analyst...

# STEP 0: GLOBAL HARD RULES
- Always validate entities...
- Use NULLIF for division...

# STEP 1: CLASSIFY THE USER QUERY TYPE
[TYPE A] Named Territory Group...
[TYPE B] Single Market...

# STEP 2: DATASET / TABLES
TABLE 1: dataset.table_name...

# STEP 3: KPI DEFINITIONS
comp_sales_perc := ROUND(...)

# STEP 4: SQL TEMPLATES
TEMPLATE A: ...
```

## Tips

- Keep prompts clear, structured, and comprehensive
- Include specific examples for common query types
- Define all KPI formulas explicitly
- Provide SQL templates that can be adapted
- Document any critical business rules or constraints
