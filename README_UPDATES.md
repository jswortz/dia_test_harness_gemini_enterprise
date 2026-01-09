# README Updates - DIA_AGENT_ID Highlighting

## Changes Made

Updated README.md to prominently highlight the critical step of copying the DIA_AGENT_ID after deployment.

### 1. Configuration Section
**Added**:
- Warning comment in .env example: `DIA_AGENT_ID=  # ⚠️ ADD THIS AFTER DEPLOYING`
- Note explaining it will be populated after Step 1

### 2. Step 1: Deploy Agent
**Added prominent callout box**:
```
🚨 CRITICAL STEP - DO THIS NOW:

Copy the Agent ID from the output above and add it to your .env file:

  echo "DIA_AGENT_ID=6970595320594450988" >> .env

Or manually edit .env to add:
  DIA_AGENT_ID=6970595320594450988

⚠️ Without this step, the optimize command will not find your agent!
```

### 3. Configuration File Section
**Updated**:
- Clarified agent identification methods
- Explained DIA_AGENT_ID (recommended) vs display_name (fallback)
- Emphasized exact matching requirement

### 4. Troubleshooting Section
**Enhanced**:
- Made "Agent Not Found" error the first item
- Listed DIA_AGENT_ID as the **Most Common** cause
- Provided clear checking steps
- Explained the display_name fallback mechanism
- Added tips for missing charts/reports

## Why These Changes Matter

**Before**: Users would deploy an agent, skip copying the ID, then get "Agent Not Found" errors when running optimize.

**After**: Users see multiple prominent warnings and clear instructions to copy the agent ID immediately after deployment.

## Visual Emphasis Used

- 🚨 emoji for critical steps
- ⚠️ emoji for warnings
- **Bold text** for emphasis
- Clear code blocks with exact commands
- Callout boxes separating critical steps

## User Flow Improved

1. See DIA_AGENT_ID in initial .env template ✅
2. Deploy agent
3. See CRITICAL STEP callout box immediately ✅
4. Copy/paste exact command or manual edit instructions ✅
5. Proceed to authorization
6. If stuck, troubleshooting section lists this as #1 cause ✅

All critical touchpoints covered!
