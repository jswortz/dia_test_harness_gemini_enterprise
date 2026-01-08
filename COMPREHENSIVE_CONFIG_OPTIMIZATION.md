# Comprehensive Configuration Field Optimization

## Overview

The optimization workflow has been enhanced to analyze and improve **ALL** configuration fields, not just the `nl2sql_prompt`. This provides much more comprehensive and intelligent agent optimization.

## Architecture

### 1. ConfigFieldAnalyzer (`src/iterative/config_analyzer.py`)

**Purpose**: AI-powered analysis to determine which configuration fields need improvement

**Capabilities**:
- Analyzes test failures against current configuration
- Provides field-by-field recommendations with:
  - `should_modify`: Whether to change this field
  - `rationale`: Why this field should/shouldn't be modified
  - `priority`: Importance level (1-5)
  - `suggested_value`: Concrete suggestion if modification recommended

**Analyzable Fields**:
1. **nl2sql_prompt** - Main SQL generation instructions (HIGH priority)
2. **schema_description** - Database schema details (HIGH priority)
3. **nl2sql_examples** - Few-shot learning examples (MEDIUM priority)
4. **nl2py_prompt** - Python processing instructions (LOW priority)
5. **allowed_tables** - Table access whitelist (MEDIUM priority)
6. **blocked_tables** - Table access blacklist (MEDIUM priority)

### 2. Enhanced IterativeOptimizer

**Changes to `src/iterative/optimizer.py`**:

#### New Attributes:
- `config_analyzer`: Instance of ConfigFieldAnalyzer
- `current_config`: Full configuration dict (not just prompt)
- `config_changes_description`: Tracks all field changes

#### Enhanced `_improve_prompt()` Method:

**Old behavior**: Only analyzed and improved `nl2sql_prompt`

**New behavior**:
1. Uses ConfigFieldAnalyzer to analyze ALL fields
2. Displays prioritized recommendations for each field
3. Uses PromptImprover for `nl2sql_prompt` (backward compatible)
4. Applies AI suggestions for other high-priority fields
5. In auto-accept mode: Automatically applies all medium+ priority suggestions
6. In manual mode: Prompts user to review each suggested change
7. Updates `self.current_config` with all changes
8. Returns full change description

#### Enhanced Agent Update:

**Old code**:
```python
self.deployer.update_prompt(improved_prompt, self.current_params)
```

**New code**:
```python
self.deployer.update_prompt(
    new_prompt=improved_prompt,
    params=self.current_params,
    full_config=self.current_config  # Pass ALL fields
)
```

This ensures all configuration changes are deployed to the agent, not just the prompt.

### 3. Enhanced Reporting

**Changes to `src/iterative/report_generator.py`**:

#### Iteration Details Section:
Now displays ALL config fields with their values:
- **nl2sql_prompt**: Preview + character count
- **schema_description**: Preview + character count
- **nl2sql_examples**: Number of examples
- **nl2py_prompt**: Set/Not set + character count
- **allowed_tables**: Count of whitelisted tables
- **blocked_tables**: Count of blocked tables
- **Changes Made**: Description of what changed

#### Configuration Evolution Table:
Expanded from just "Prompt Length" to comprehensive tracking:

| Iter | Train | Test | Prompt | Schema | Examples | Py Prompt | Tables |
|------|-------|------|--------|--------|----------|-----------|--------|
| 0    | 60.0% | 70.0% | 377ch  | 0ch    | 0ex      | No        | All    |
| 1    | 75.0% | 80.0% | 456ch  | 250ch  | 3ex      | No        | A:5/B:2|

**Legend**:
- Prompt/Schema: Character count
- Examples: Number of few-shot examples (ex)
- Py Prompt: Whether nl2py_prompt is set
- Tables: A=Allowed count, B=Blocked count

### 4. Enhanced Deployer Integration

**`src/iterative/deployer.py`** already supports `full_config` parameter:

```python
def update_prompt(self, new_prompt: str, params: Dict = None, full_config: Dict = None):
    nl_query_config = {"nl2sqlPrompt": new_prompt}

    if full_config:
        if full_config.get("schema_description"):
            nl_query_config["schemaDescription"] = full_config["schema_description"]
        if full_config.get("nl2py_prompt"):
            nl_query_config["nl2pyPrompt"] = full_config["nl2py_prompt"]
        if full_config.get("nl2sql_examples"):
            nl_query_config["nl2sqlExamples"] = full_config["nl2sql_examples"]

    # PATCH request with all fields
```

## User Experience

### Iteration Flow

1. **Test Execution**: Agent tested against golden set
2. **Failure Analysis**: AI analyzes failures
3. **Field Recommendations**: AI determines which fields to modify

Example output:
```
📋 Recommended Configuration Changes (3 fields):

🔴 CRITICAL nl2sql_prompt:
  Reason: Agent is over-selecting columns (SELECT *). Need explicit guidance to select only requested fields.

🟡 MEDIUM schema_description:
  Reason: Missing information about customer_orders table relationships. Agent needs better schema context.

🟡 MEDIUM nl2sql_examples:
  Reason: No examples of JOIN patterns. Adding few-shot examples would help with relationship queries.
```

4. **Improvement Generation**:
   - PromptImprover generates improved `nl2sql_prompt`
   - ConfigFieldAnalyzer provides suggested values for other fields

5. **User Approval** (manual mode):
   - Shows diff for prompt changes
   - Asks approval for each other field

6. **Auto-Accept** (auto mode):
   - Automatically applies all medium+ priority suggestions
   - No manual intervention needed

7. **Deployment**: All approved changes deployed via PATCH API

8. **Reporting**: All config changes tracked in trajectory and report

### Auto-Accept Mode

With `--auto-accept` flag:
- ALL configuration fields analyzed automatically
- Medium+ priority suggestions applied without prompts
- Full configuration deployed to agent
- Changes tracked in report

Perfect for fully automated optimization pipelines.

## Benefits

### Before (Prompt-Only Optimization):
- ❌ Only improved nl2sql_prompt
- ❌ Ignored schema_description improvements
- ❌ Couldn't add few-shot examples automatically
- ❌ No table access control optimization
- ❌ Limited improvement potential

### After (Comprehensive Config Optimization):
- ✅ Analyzes ALL 6 configuration fields
- ✅ Prioritizes changes based on failure analysis
- ✅ Can add schema descriptions when needed
- ✅ Can add few-shot examples for specific patterns
- ✅ Can adjust table access controls
- ✅ Much higher improvement potential
- ✅ Complete config change tracking in reports

## Configuration File Requirements

Ensure your `baseline_config.json` includes all optimizable fields:

```json
{
  "name": "baseline",
  "display_name": "Data Agent - Baseline",
  "description": "Baseline Data Insights Agent for NL2SQL",

  "nl2sql_prompt": "You are an expert SQL assistant...",
  "schema_description": "The dataset contains...",
  "nl2sql_examples": [
    {
      "query": "How many customers?",
      "expected_sql": "SELECT COUNT(*) FROM customers",
      "expected_response": "There are X customers."
    }
  ],
  "nl2py_prompt": null,

  "bq_project_id": "${GOOGLE_CLOUD_PROJECT}",
  "bq_dataset_id": "${BQ_DATASET_ID}",

  "allowed_tables": [],
  "blocked_tables": []
}
```

Even if fields are empty/null initially, AI can populate them during optimization.

## Example Optimization Run

```bash
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --max-iterations 10 \
  --auto-accept
```

**Iteration 1**:
- Train: 60% accuracy
- AI identifies: nl2sql_prompt needs better column selection guidance
- AI adds: Instruction to "SELECT only requested columns, avoid SELECT *"
- Deploy: Updated nl2sql_prompt

**Iteration 2**:
- Train: 70% accuracy
- AI identifies: schema_description missing (failures on JOINs)
- AI adds: Schema description explaining table relationships
- Deploy: Updated nl2sql_prompt + schema_description

**Iteration 3**:
- Train: 80% accuracy
- AI identifies: nl2sql_examples would help with aggregation patterns
- AI adds: 3 examples showing COUNT, SUM, GROUP BY patterns
- Deploy: Updated nl2sql_prompt + schema_description + nl2sql_examples

**Final Report** shows complete evolution of all fields across iterations.

## Testing

To test the comprehensive config optimization:

```bash
# Deploy agent
dia-harness deploy --config-file configs/baseline_config.json

# Authorize via Gemini Enterprise UI (one-time)

# Run optimization with all config field analysis
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --max-iterations 6 \
  --num-repeats 3 \
  --auto-accept

# Check report to see all config field changes
cat results/OPTIMIZATION_REPORT_*.md
```

The report will show:
- Which fields were modified in each iteration
- Why each field was modified
- Character counts and example counts for each field
- Complete configuration evolution table

## API Fields Supported

All Data Insights Agent API fields are supported for optimization:

**Agent Configuration API Fields**:
- `nl2sqlPrompt` → `nl2sql_prompt`
- `schemaDescription` → `schema_description`
- `nl2sqlExamples` → `nl2sql_examples`
- `nl2pyPrompt` → `nl2py_prompt`
- Table access controls (via allowed_tables/blocked_tables)

**Preserved Fields** (not modified by optimizer):
- `bq_project_id`
- `bq_dataset_id`
- `display_name`
- `description`
- `icon_uri`
- `tool_description`

## Backward Compatibility

- All previous trajectory JSON files work with backward compatibility in report generator
- Old optimization runs that only modified `nl2sql_prompt` still generate correct reports
- New runs show comprehensive config field tracking
- Existing configs without some fields (e.g., no `schema_description`) work fine

## Future Enhancements

Potential additions:
- **Config diffing**: Show exact diffs for schema_description and examples
- **Field history**: Track when each field was last modified
- **Priority tuning**: Allow users to customize field priorities
- **Rollback**: Ability to revert specific field changes
- **A/B testing**: Test different field combinations
