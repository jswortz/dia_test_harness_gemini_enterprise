#!/usr/bin/env python3
"""
Update an existing DIA agent's configuration from baseline_config.json.

Reads environment variables from .env and updates the agent specified by DIA_AGENT_ID
with the configuration from configs/baseline_config.json.

Supported fields for update:
- displayName (from 'name' or 'display_name')
- description
- tool_description (via managedAgentDefinition.toolSettings.toolDescription)
- nl2sql_prompt
- schema_description
- nl2py_prompt
- nl2sql_examples
- allowlistTables (from 'allowed_tables' in config)

Note: bq_project_id and bq_dataset_id are IMMUTABLE after agent creation and cannot be updated.
Note: blocked_tables is NOT supported by the API.
"""

import os
import sys
import json
import argparse
import requests
import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import quote

# Load environment variables
load_dotenv()

# Required environment variables
REQUIRED_ENV_VARS = [
    "GOOGLE_CLOUD_PROJECT",
    "DIA_LOCATION",
    "DIA_ENGINE_ID",
    "DIA_AGENT_ID",
]

# Optional environment variables (not used for update, but good to have)
OPTIONAL_ENV_VARS = [
    "BQ_DATASET_ID",
    "OAUTH_CLIENT_ID",
    "OAUTH_SECRET",
]


def get_env_vars():
    """Load and validate required environment variables."""
    env_vars = {}
    missing = []
    
    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var)
        if not value:
            missing.append(var)
        else:
            env_vars[var] = value
    
    if missing:
        print(f"❌ Missing required environment variables: {', '.join(missing)}")
        print("\nPlease ensure your .env file contains:")
        for var in REQUIRED_ENV_VARS:
            print(f"  {var}=<value>")
        sys.exit(1)
    
    # Load optional vars (don't fail if missing)
    for var in OPTIONAL_ENV_VARS:
        env_vars[var] = os.getenv(var)
    
    return env_vars


def get_auth_headers(project_id: str) -> dict:
    """Get authentication headers for API requests."""
    creds, _ = google.auth.default(quota_project_id=project_id)
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def get_api_host(location: str) -> str:
    """Get the appropriate API host based on location."""
    if location.lower() == "global":
        return "discoveryengine.googleapis.com"
    return f"{location.lower()}-discoveryengine.googleapis.com"


def build_agent_name(project_id: str, location: str, engine_id: str, agent_id: str) -> str:
    """Build the full agent resource name."""
    return (
        f"projects/{project_id}/locations/{location}/collections/default_collection/"
        f"engines/{engine_id}/assistants/default_assistant/agents/{agent_id}"
    )


def verify_agent_exists(host: str, agent_name: str, headers: dict) -> dict:
    """Verify the agent exists and return current config."""
    url = f"https://{host}/v1alpha/{agent_name}"
    
    print(f"🔍 Verifying agent exists: {agent_name.split('/')[-1]}")
    resp = requests.get(url, headers=headers)
    
    if resp.status_code == 404:
        print(f"❌ Agent not found: {agent_name}")
        sys.exit(1)
    elif resp.status_code != 200:
        print(f"❌ Failed to fetch agent: {resp.status_code} - {resp.text}")
        sys.exit(1)
    
    agent_data = resp.json()
    print(f"✓ Found agent: {agent_data.get('displayName', 'Unknown')}")
    return agent_data


def build_update_payload(config: dict, only_fields: list = None) -> tuple[dict, list]:
    """
    Build the PATCH payload and update mask from config.
    
    Args:
        config: Configuration dictionary
        only_fields: If provided, only include these fields in the update.
                     Valid values: displayName, description, tool_description,
                     nl2sql_prompt, schema_description, nl2py_prompt, nl2sql_examples,
                     allowlistTables
    
    Returns:
        tuple: (payload dict, list of update mask fields)
    """
    payload = {}
    update_mask_fields = []
    
    # Helper to check if field should be included
    def should_include(field_name: str) -> bool:
        if only_fields is None:
            # For immutable fields, only include if explicitly requested
            if field_name in ["bqProjectId", "bqDatasetId"]:
                return False
            return True
        return field_name in only_fields
    
    # 1. Display Name (use 'display_name' if present, otherwise 'name')
    if should_include("displayName"):
        display_name = config.get("display_name") or config.get("name")
        if display_name:
            payload["displayName"] = display_name
            update_mask_fields.append("displayName")
            print(f"  ✓ displayName: {display_name}")
        else:
            print(f"  ⚠ displayName: not set in config")
    else:
        print(f"  ⏭ displayName: SKIPPED (not in --only list)")
    
    # 2. Description
    if should_include("description"):
        description = config.get("description")
        if description:
            payload["description"] = description
            update_mask_fields.append("description")
            print(f"  ✓ description: {description[:50]}..." if len(description) > 50 else f"  ✓ description: {description}")
        else:
            print(f"  ⚠ description: not set in config")
    else:
        print(f"  ⏭ description: SKIPPED (not in --only list)")
    
    # 3. Build managed_agent_definition structure
    managed_def = {}
    
    # 3a. Tool Settings
    if should_include("tool_description"):
        tool_description = config.get("tool_description")
        if tool_description:
            managed_def["tool_settings"] = {
                "tool_description": tool_description
            }
            update_mask_fields.append("managedAgentDefinition.toolSettings.toolDescription")
            print(f"  ✓ tool_description: {tool_description[:50]}..." if len(tool_description) > 50 else f"  ✓ tool_description: {tool_description}")
        else:
            print(f"  ⚠ tool_description: not set in config")
    else:
        print(f"  ⏭ tool_description: SKIPPED (not in --only list)")
    
    # 3b. NL Query Config (within data_science_agent_config)
    nl_query_config = {}
    nl_query_fields_included = []
    
    # nl2sql_prompt
    if should_include("nl2sql_prompt"):
        nl2sql_prompt = config.get("nl2sql_prompt")
        if nl2sql_prompt:
            nl_query_config["nl2sqlPrompt"] = nl2sql_prompt
            nl_query_fields_included.append("nl2sqlPrompt")
            print(f"  ✓ nl2sql_prompt: {len(nl2sql_prompt)} chars")
        else:
            print(f"  ⚠ nl2sql_prompt: not set in config")
    else:
        print(f"  ⏭ nl2sql_prompt: SKIPPED (not in --only list)")
    
    # schema_description
    if should_include("schema_description"):
        schema_description = config.get("schema_description")
        if schema_description:
            nl_query_config["schemaDescription"] = schema_description
            nl_query_fields_included.append("schemaDescription")
            print(f"  ✓ schema_description: {len(schema_description)} chars")
        else:
            print(f"  ⚠ schema_description: not set in config")
    else:
        print(f"  ⏭ schema_description: SKIPPED (not in --only list)")
    
    # nl2py_prompt (optional, can be null)
    if should_include("nl2py_prompt"):
        nl2py_prompt = config.get("nl2py_prompt")
        if nl2py_prompt:
            nl_query_config["nl2pyPrompt"] = nl2py_prompt
            nl_query_fields_included.append("nl2pyPrompt")
            print(f"  ✓ nl2py_prompt: {len(nl2py_prompt)} chars")
        else:
            print(f"  ⚠ nl2py_prompt: not set in config (or null)")
    else:
        print(f"  ⏭ nl2py_prompt: SKIPPED (not in --only list)")
    
    # nl2sql_examples (optional, can be empty list)
    if should_include("nl2sql_examples"):
        nl2sql_examples = config.get("nl2sql_examples")
        if nl2sql_examples and isinstance(nl2sql_examples, list) and len(nl2sql_examples) > 0:
            nl_query_config["nl2sqlExamples"] = nl2sql_examples
            nl_query_fields_included.append("nl2sqlExamples")
            print(f"  ✓ nl2sql_examples: {len(nl2sql_examples)} examples")
        else:
            print(f"  ⚠ nl2sql_examples: not set in config (or empty)")
    else:
        print(f"  ⏭ nl2sql_examples: SKIPPED (not in --only list)")
    
    # Add nl_query_config to managed_def if any fields were set
    if nl_query_config:
        if "data_science_agent_config" not in managed_def:
            managed_def["data_science_agent_config"] = {}
        managed_def["data_science_agent_config"]["nl_query_config"] = nl_query_config
        update_mask_fields.append("managedAgentDefinition.dataScienceAgentConfig.nlQueryConfig")
    
    # 3c. Allowlist Tables (within data_science_agent_config)
    if should_include("allowlistTables"):
        allowed_tables = config.get("allowed_tables")
        if allowed_tables and isinstance(allowed_tables, list) and len(allowed_tables) > 0:
            if "data_science_agent_config" not in managed_def:
                managed_def["data_science_agent_config"] = {}
            managed_def["data_science_agent_config"]["allowlistTables"] = allowed_tables
            update_mask_fields.append("managedAgentDefinition.dataScienceAgentConfig.allowlistTables")
            print(f"  ✓ allowlistTables: {len(allowed_tables)} tables")
        else:
            print(f"  ⚠ allowlistTables: not set in config (or empty)")
    else:
        print(f"  ⏭ allowlistTables: SKIPPED (not in --only list)")
    
    # 3d. BQ Project ID (within data_science_agent_config) - Only if explicitly requested
    if should_include("bqProjectId"):
        bq_project_id = config.get("bq_project_id")
        if bq_project_id:
            if "data_science_agent_config" not in managed_def:
                managed_def["data_science_agent_config"] = {}
            managed_def["data_science_agent_config"]["bqProjectId"] = bq_project_id
            update_mask_fields.append("managedAgentDefinition.dataScienceAgentConfig.bqProjectId")
            print(f"  ✓ bqProjectId: {bq_project_id}")
        else:
            print(f"  ⚠ bqProjectId: not set in config")
    else:
        if only_fields is None and config.get("bq_project_id"):
            print(f"  ⚠ bq_project_id: SKIPPED (immutable after creation - use --only bqProjectId to attempt update)")
    
    # 3e. BQ Dataset ID (within data_science_agent_config) - Only if explicitly requested
    if should_include("bqDatasetId"):
        bq_dataset_id = config.get("bq_dataset_id")
        if bq_dataset_id:
            if "data_science_agent_config" not in managed_def:
                managed_def["data_science_agent_config"] = {}
            managed_def["data_science_agent_config"]["bqDatasetId"] = bq_dataset_id
            update_mask_fields.append("managedAgentDefinition.dataScienceAgentConfig.bqDatasetId")
            print(f"  ✓ bqDatasetId: {bq_dataset_id}")
        else:
            print(f"  ⚠ bqDatasetId: not set in config")
    else:
        if only_fields is None and config.get("bq_dataset_id"):
            print(f"  ⚠ bq_dataset_id: SKIPPED (immutable after creation - use --only bqDatasetId to attempt update)")
    
    # Add managed_agent_definition to payload if any fields were set
    if managed_def:
        payload["managed_agent_definition"] = managed_def
        if config.get("blocked_tables"):
            print(f"  ⚠ blocked_tables: SKIPPED (not supported by API)")
        if config.get("icon_uri"):
            print(f"  ⚠ icon_uri: SKIPPED (use separate update)")
    
    return payload, update_mask_fields


def update_agent(
    host: str,
    agent_name: str,
    payload: dict,
    update_mask_fields: list,
    headers: dict
) -> bool:
    """Send PATCH request to update the agent."""
    
    # Build update mask (URL-encoded)
    update_mask = ",".join(update_mask_fields)
    encoded_mask = quote(update_mask, safe='')
    
    url = f"https://{host}/v1alpha/{agent_name}?updateMask={encoded_mask}"
    
    print(f"\n📤 Sending PATCH request...")
    print(f"  Update mask: {update_mask}")
    
    resp = requests.patch(url, headers=headers, json=payload)
    
    if resp.status_code != 200:
        print(f"❌ PATCH failed: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return False
    
    print("✓ PATCH successful")
    
    # Check if LRO was returned
    data = resp.json()
    if "name" in data and "operations" in data["name"]:
        print("  ⚠ LRO returned - operation may still be in progress")
        print("  Note: Configuration update was submitted successfully")
    
    return True


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Update an existing DIA agent's configuration from baseline_config.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update all fields from config
  python update_agent_config.py --yes

  # Update ONLY displayName
  python update_agent_config.py --yes --only displayName

  # Update ONLY displayName and description
  python update_agent_config.py --yes --only displayName description

  # Update ONLY nl2sql_prompt
  python update_agent_config.py --yes --only nl2sql_prompt

Available fields for --only:
  displayName, description, tool_description, nl2sql_prompt, 
  schema_description, nl2py_prompt, nl2sql_examples, allowlistTables,
  bqProjectId, bqDatasetId
"""
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt and proceed with update"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: configs/baseline_config.json)"
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=[
            "displayName", "description", "tool_description",
            "nl2sql_prompt", "schema_description", "nl2py_prompt", "nl2sql_examples",
            "allowlistTables", "bqProjectId", "bqDatasetId"
        ],
        help="Update ONLY these specific fields (space-separated list)"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    print("=" * 80)
    print("DIA Agent Configuration Updater")
    print("=" * 80)
    
    # 1. Load environment variables
    print("\n📋 Loading environment variables...")
    env = get_env_vars()
    
    project_id = env["GOOGLE_CLOUD_PROJECT"]
    location = env["DIA_LOCATION"]
    engine_id = env["DIA_ENGINE_ID"]
    agent_id = env["DIA_AGENT_ID"]
    
    print(f"  Project: {project_id}")
    print(f"  Location: {location}")
    print(f"  Engine ID: {engine_id}")
    print(f"  Agent ID: {agent_id}")
    
    # 2. Load config file
    if args.config:
        config_path = Path(args.config)
    else:
        script_dir = Path(__file__).parent
        config_path = script_dir.parent / "configs" / "baseline_config.json"
    
    print(f"\n📄 Loading config from: {config_path}")
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)
    
    config = load_config(config_path)
    print(f"✓ Config loaded: {config.get('name', 'unnamed')}")
    
    # 3. Build API components
    host = get_api_host(location)
    agent_name = build_agent_name(project_id, location, engine_id, agent_id)
    headers = get_auth_headers(project_id)
    
    # 4. Verify agent exists
    print()
    current_agent = verify_agent_exists(host, agent_name, headers)
    
    # 5. Build update payload
    if args.only:
        print(f"\n📦 Building update payload (--only: {', '.join(args.only)})...")
    else:
        print("\n📦 Building update payload (all fields)...")
    payload, update_mask_fields = build_update_payload(config, only_fields=args.only)
    
    if not update_mask_fields:
        print("⚠ No fields to update!")
        sys.exit(0)
    
    # 6. Show summary and confirm
    print(f"\n" + "=" * 80)
    print("Summary of changes:")
    print("=" * 80)
    print(f"Agent: {current_agent.get('displayName', 'Unknown')} -> {payload.get('displayName', '(unchanged)')}")
    print(f"Fields to update: {', '.join(update_mask_fields)}")
    
    # Ask for confirmation (skip if --yes flag provided)
    if not args.yes:
        response = input("\n⚠ Proceed with update? [y/N]: ").strip().lower()
        if response != 'y':
            print("Aborted.")
            sys.exit(0)
    else:
        print("\n✓ Auto-confirmed via --yes flag")
    
    # 7. Update agent
    if not update_agent(host, agent_name, payload, update_mask_fields, headers):
        print("\n❌ Update failed!")
        sys.exit(1)
    
    print("\n" + "=" * 80)
    print("✅ Agent configuration updated successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
