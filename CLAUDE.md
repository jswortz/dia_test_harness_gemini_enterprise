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
python scripts/generate_data.py

# Load data into BigQuery
python scripts/load_to_bq.py

# Generate golden test set
python scripts/generate_golden_set.py
```

### Agent Deployment
```bash
# Deploy all 5 agent variants (uses delete-and-recreate strategy)
python scripts/deploy_data_agent.py
```

### Testing and Evaluation

**IMPORTANT: OAuth Authorization Required First**

Before running evaluations, agents must be authorized to access BigQuery:

```bash
# Generate OAuth authorization URL for your agent
python scripts/authorize_agent.py

# This will:
# 1. Query the agent to trigger authorization requirements
# 2. Extract and display the OAuth authorization URL
# 3. Save the URL to results/authorization_1.txt
# 4. Provide step-by-step instructions to authorize

# After visiting the URL and authorizing, proceed with tests:
```

Then run evaluation tests:

```bash
# Test the evaluation pipeline with debug set (single question)
python scripts/test_evaluation.py

# Run golden test evaluations (full test suite)
python scripts/run_golden_test.py

# Run the test harness CLI (orchestrator)
dia-harness run-all --config-file configs/multi_variant.json --golden-set data/golden_set.json --use-real-api

# Debug specific agent queries
python scripts/debug_agent_query.py
```

### Inspection and Verification
```bash
# Check environment variables
python scripts/check_env.py

# Inspect engine configuration
python scripts/inspect_engine.py

# Inspect assistant configuration
python scripts/inspect_assistant.py

# Inspect specific agent
python scripts/inspect_agent_name.py

# Check Long-Running Operations (LRO) status
python scripts/check_lro.py

# Verify API connectivity
python scripts/verify_connectivity.py

# Example: Query a specific agent with agentsSpec (shows correct usage)
AGENT_ID=your-agent-id python scripts/example_query_agent.py
```

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

- `configs/multi_variant.json`: 5 agent configurations for parallel testing
- `src/orchestrator/main.py`: CLI entry point (`dia-harness` command)
- `src/orchestrator/engine.py`: TestEngine orchestrates parallel config evaluation
- `src/orchestrator/agent_client.py`: Agent deployment and querying (persistent engine model)
- `src/evaluation/runner.py`: Golden set test execution with session follow-up
- `src/evaluation/evaluator.py`: SQL comparison and LLM-based judgement
- `src/evaluation/agent_client.py`: Agent query client with `agentsSpec` routing
- `scripts/deploy_data_agent.py`: Multi-variant deployment with OAuth authorization
- `scripts/authorize_agent.py`: **OAuth authorization URL generator** - run this first before evaluations
- `scripts/test_evaluation.py`: Full evaluation pipeline test with single test case
- `scripts/run_golden_test.py`: Execute full golden set evaluation

## Documentation References

The `.agent/rules/` directory contains references to external documentation:
- Data Insights Agent API: https://docs.cloud.google.com/gemini/enterprise/docs/data-agent
- Gemini Enterprise API reference: https://docs.cloud.google.com/generative-ai-app-builder/docs/reference/rest

Consult these when working with API calls or authentication flows.
