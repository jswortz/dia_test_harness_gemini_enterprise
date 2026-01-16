# Schema Description

This file contains the detailed database schema documentation for the agent.

## Purpose

This document provides comprehensive information about the database schema, including:

- Table structures and relationships
- Column definitions and data types
- Business logic and field semantics
- Join patterns and best practices
- Critical data quality rules and constraints
- Field naming conventions

## Usage

This file is read by `scripts/populate_config_from_markdown.py` and its contents are used to populate the `schema_description` field in `configs/baseline_config.json`.

## How to Edit

1. Write or update your schema documentation in this markdown file
2. Run: `python scripts/populate_config_from_markdown.py`
3. The script will automatically update `baseline_config.json` with the new schema description

## Example Structure

```
# DATABASE SCHEMA DOCUMENTATION
Dataset: project.dataset_name

## GLOBAL SQL GUARDRAILS
1) Always validate entities before filtering
2) Rounding / numeric conventions
3) Terminology definitions

## TABLE 1: fact_table_name
Purpose: Primary fact table for...
Grain: One row per X + Y

### Identifiers
field_1 (data_type) - Description and usage notes
field_2 (data_type) - Description and usage notes

### Metrics
metric_1 (data_type) - Description, calculation, when to use
metric_2 (data_type) - Description, calculation, when to use

## TABLE 2: dimension_table_name
Purpose: Dimension providing...
...

## KPI / METRIC CALCULATION RECIPES
Comp Sales % = (TY - LY) / LY * 100
Average Check = Sales / Transactions
...
```

## Tips

- Document all tables, even auxiliary/dimension tables
- Clearly explain grain (one row represents...)
- Note any many-to-many relationships or join risks
- Include business definitions for all KPIs
- Document any data quality issues or edge cases
- Provide context for when to use specific fields
