# Tool Description

This file contains the high-level description of the agent/tool.

## Purpose

This is a concise, user-facing description of what the agent does and what it can be used for. It should:

- Explain the agent's primary purpose
- Describe the types of questions it can answer
- Mention the data sources it connects to
- Outline key capabilities and use cases
- Set appropriate expectations for users

## Usage

This file is read by `scripts/populate_config_from_markdown.py` and its contents are used to populate the `tool_description` field in `configs/baseline_config.json`.

The tool description is also used in the agent configuration and may be displayed to users when they interact with the agent.

## How to Edit

1. Write or update your tool description in this markdown file
2. Run: `python scripts/populate_config_from_markdown.py`
3. The script will automatically update `baseline_config.json` with the new tool description

## Example Content

```
A [Company Name] [Domain] analyst agent that converts natural-language questions 
into accurate BigQuery SQL against the [Dataset Name] datasets. 

Use it to retrieve and analyze [key metrics] across [dimensions] and time periods, 
returning consistent, authoritative metrics suitable for reporting and analytics.

Key capabilities:
- Analyze sales, revenue, and KPIs
- Compare time periods (YoY, QoQ, etc.)
- Aggregate by territory, market, channel, etc.
- Calculate comp metrics and growth rates
```

## Tips

- Keep it concise (2-4 sentences ideal)
- Focus on what the agent can DO, not how it works
- Use business-friendly language (avoid technical jargon)
- Mention specific use cases or metric types
- Align with user expectations and needs
