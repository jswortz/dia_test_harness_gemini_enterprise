# OAuth Authorization Guide for Data Insights Agents

## Overview

Data Insights Agents require OAuth authorization to access BigQuery. This is a one-time setup per agent required by the v1alpha API.

## Why Authorization is Needed

When you query a Data Insights Agent that needs to access BigQuery:

1. The agent receives your question via `agentsSpec` routing ✅
2. The agent identifies it needs to query BigQuery ✅
3. The agent checks for OAuth authorization ❌
4. **Without authorization**: Returns `requiredAuthorizations` with OAuth URL
5. **With authorization**: Executes SQL and returns results

## Quick Start

### Step 1: Generate Authorization URL

```bash
python scripts/authorize_agent.py
```

**Output:**
```
======================================================================
⚠️  AUTHORIZATION REQUIRED
======================================================================

Your Data Insights Agent needs authorization to access BigQuery.
Please visit the URL(s) below to grant access:

--- Authorization 1 ---
Resource: projects/.../authorizations/auth-xxxxx
Display Name: auth-xxxxx

Authorization URL:
https://accounts.google.com/o/oauth2/v2/auth?client_id=...

Steps to authorize:
  1. Copy the URL above
  2. Paste it into your browser
  3. Sign in with your Google account
  4. Grant the requested permissions (BigQuery access)
  5. You'll be redirected to a confirmation page
  6. Re-run your evaluation tests after authorization

  ✓ URL saved to: results/authorization_1.txt
```

### Step 2: Visit the Authorization URL

1. Copy the displayed URL
2. Open it in your browser
3. Sign in with your Google account (must have BigQuery access)
4. Review the requested permissions:
   - **Scope**: `https://www.googleapis.com/auth/bigquery`
   - **Purpose**: Allow agent to query BigQuery datasets
5. Click "Allow" or "Grant"
6. You'll be redirected to: `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`
7. See confirmation message

### Step 3: Verify Authorization

Run the authorization script again to confirm:

```bash
python scripts/authorize_agent.py
```

**Expected output:**
```
======================================================================
✓ AGENT IS AUTHORIZED
======================================================================

Your agent is already authorized and returned a response!
You can now run evaluation tests without authorization issues.

Sample response:
  There are 1000 customers in the database.
```

### Step 4: Run Evaluations

Now you can run automated tests:

```bash
# Test with a single question
python scripts/test_evaluation.py

# Run full golden set
python scripts/run_golden_test.py
```

## Troubleshooting

### "Agent does not exist" Error

**Problem**: The `DIA_AGENT_ID` in `.env` doesn't match an existing agent.

**Solution**:
```bash
# List available agents
python scripts/inspect_agent_name.py

# Update .env with a valid agent ID
# Example: DIA_AGENT_ID=16994088282440686170
```

### Authorization URL Doesn't Work

**Problem**: URL returns "Invalid request" or similar error.

**Possible causes**:
1. OAuth credentials in `.env` are incorrect
2. Redirect URI mismatch
3. OAuth consent screen not configured

**Solution**:
1. Verify `OAUTH_CLIENT_ID` and `OAUTH_SECRET` in `.env`
2. Ensure OAuth consent screen is configured in Google Cloud Console
3. Verify redirect URI: `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`

### Agent Returns Empty SQL

**Problem**: After authorization, agent still doesn't generate SQL.

**Possible causes**:
1. Authorization not yet propagated (wait a few minutes)
2. BigQuery dataset doesn't exist
3. Agent configuration missing dataset information

**Solution**:
```bash
# Check agent configuration
python scripts/inspect_specific_agent.py

# Verify dataScienceAgentConfig includes:
# - bqProjectId
# - bqDatasetId
# - nlQueryConfig
```

## Technical Details

### Authorization Flow

1. **Request Structure**:
```json
{
  "session": "projects/.../sessions/-",
  "query": {"text": "How many customers?"},
  "agentsSpec": {
    "agentSpecs": [{"agentId": "123"}]
  }
}
```

2. **Response Without Authorization**:
```json
{
  "answer": {
    "state": "SUCCEEDED",
    "requiredAuthorizations": [
      {
        "authorization": "projects/.../authorizations/auth-xxx",
        "authorizationUri": "https://accounts.google.com/o/oauth2/v2/auth?..."
      }
    ]
  }
}
```

3. **Response With Authorization**:
```json
{
  "answer": {
    "state": "SUCCEEDED",
    "replies": [
      {
        "groundedContent": {
          "content": {
            "text": "There are 1000 customers.",
            "thought": false
          }
        }
      }
    ]
  }
}
```

### Authorization Persistence

- **Scope**: Per agent resource
- **Duration**: Until explicitly revoked
- **Storage**: Google OAuth token service
- **Refresh**: Automatic via refresh token

### Multiple Agents

If you have multiple agents (e.g., multi-variant testing), you need to authorize each one:

```bash
# Set agent ID for baseline variant
export DIA_AGENT_ID=16994088282440686170
python scripts/authorize_agent.py

# Set agent ID for few-shot variant
export DIA_AGENT_ID=2585432156173393023
python scripts/authorize_agent.py

# Repeat for each agent variant...
```

## Related Scripts

- `scripts/authorize_agent.py` - Generate authorization URLs
- `scripts/test_evaluation.py` - Test evaluation pipeline
- `scripts/inspect_specific_agent.py` - View agent configuration
- `scripts/inspect_agent_name.py` - List all agents
- `scripts/debug_agent_response.py` - Debug agent responses

## References

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [BigQuery API Scopes](https://developers.google.com/identity/protocols/oauth2/scopes#bigquery)
- [Data Insights Agent Documentation](https://cloud.google.com/gemini/enterprise/docs/data-agent)
