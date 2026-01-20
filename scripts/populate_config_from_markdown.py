#!/usr/bin/env python3
"""
Script to populate baseline_config.json fields from markdown files.

Reads:
- configs/nl2sql_prompt.md
- configs/schema_description.md
- configs/tool_description.md

Updates:
- configs/baseline_config.json (nl2sql_prompt, schema_description, tool_description, description)

Note: tool_description.md is used to populate both 'tool_description' and 'description' fields.
"""

import json
import os
from pathlib import Path


def read_markdown_file(filepath: Path) -> str:
    """Read a markdown file and return its content as a string."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"✓ Read {filepath.name} ({len(content)} characters)")
        return content
    except FileNotFoundError:
        print(f"✗ Error: File not found: {filepath}")
        raise
    except Exception as e:
        print(f"✗ Error reading {filepath}: {e}")
        raise


def load_config(filepath: Path) -> dict:
    """Load JSON config file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"✓ Loaded {filepath.name}")
        return config
    except FileNotFoundError:
        print(f"✗ Error: File not found: {filepath}")
        raise
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in {filepath}: {e}")
        raise
    except Exception as e:
        print(f"✗ Error loading {filepath}: {e}")
        raise


def save_config(config: dict, filepath: Path) -> None:
    """Save config to JSON file with proper formatting."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write('\n')  # Add trailing newline
        print(f"✓ Saved {filepath.name}")
    except Exception as e:
        print(f"✗ Error saving {filepath}: {e}")
        raise


def main():
    """Main function to populate config from markdown files."""
    # Get the project root directory (parent of scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Define file paths
    configs_dir = project_root / 'configs'
    nl2sql_prompt_file = configs_dir / 'nl2sql_prompt.md'
    schema_description_file = configs_dir / 'schema_description.md'
    tool_description_file = configs_dir / 'tool_description.md'
    baseline_config_file = configs_dir / 'baseline_config.json'
    
    print("=" * 80)
    print("Populating baseline_config.json from markdown files")
    print("=" * 80)
    print()
    
    # Read markdown files
    print("Reading markdown files...")
    nl2sql_prompt = read_markdown_file(nl2sql_prompt_file)
    schema_description = read_markdown_file(schema_description_file)
    tool_description = read_markdown_file(tool_description_file)
    print()
    
    # Load baseline config
    print("Loading baseline config...")
    config = load_config(baseline_config_file)
    print()
    
    # Update config fields
    print("Updating config fields...")
    config['nl2sql_prompt'] = nl2sql_prompt
    config['schema_description'] = schema_description
    config['tool_description'] = tool_description
    config['description'] = tool_description
    print(f"✓ Updated nl2sql_prompt ({len(nl2sql_prompt)} chars)")
    print(f"✓ Updated schema_description ({len(schema_description)} chars)")
    print(f"✓ Updated tool_description ({len(tool_description)} chars)")
    print(f"✓ Updated description ({len(tool_description)} chars) [from tool_description.md]")
    print()
    
    # Save updated config
    print("Saving updated config...")
    save_config(config, baseline_config_file)
    print()
    
    print("=" * 80)
    print("✓ SUCCESS: Config populated successfully!")
    print("=" * 80)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print()
        print("=" * 80)
        print(f"✗ FAILED: {e}")
        print("=" * 80)
        exit(1)
