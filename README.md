# Data Insights Agent (DIA) Testing Harness

A comprehensive test harness for deploying, verifying, and benchmarking Google Cloud Data Insights Agents (DIA) in parallel. This tool allows you to validate agent configurations, test data routing, and measure performance using golden datasets.

## Features

- **End-to-End Orchestration**: Manages the full lifecycle of agent testing (Setup -> Test -> Teardown).
- **Dual Modes**: 
  - **Mock Mode**: For local logic verification without API costs.
  - **Real API Mode**: Connects to live Gemini Enterprise (Discovery Engine) agents.
- **Data Generation**: Scripts to generate synthetic E-commerce datasets (Customers, Products, Orders) and Golden Test Sets.
- **Robust Verification**: Includes specialized scripts to troubleshoot `ENGINE_HAS_NO_DATA_STORES`, `404` routing errors, and API connectivity.
- **Reporting**: automatic results capture in `results.json` with latency and correctness metrics.

## Prerequisites

- Python 3.9+
- `uv` (recommended build tool) or `pip`
- Google Cloud Project with Discovery Engine API enabled
- `gcloud` CLI authenticated

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd dia_test_harness_gemini_enterprise
   ```

2. **Initialize Environment**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   GOOGLE_CLOUD_PROJECT=your-project-id
   DIA_LOCATION=global
   DIA_ENGINE_ID=your-engine-id
   DIA_AGENT_ID=your-agent-id  # Optional, usually Engine ID is sufficient
   BQ_DATASET_ID=dia_test_dataset
   ```

## Usage

### 1. Generate Data in BigQuery

Load synthetic data into your BigQuery dataset:
```bash
python scripts/load_to_bq.py
```

### 2. Run Test Suite (End-to-End)

Run the full harness using the real DIA API:
```bash
python -m src.orchestrator.main run-all \
    --config-file configs/sample_configs.json \
    --golden-set data/golden_set.json \
    --use-real-api
```

### 3. Debugging & Verification

The `scripts/` directory contains powerful tools for troubleshooting:

- **Connectivity**:
  - `scripts/debug_simple_answer.py`: Tests the working `v1beta` `:answer` endpoint.
  - `scripts/probe_agent_endpoints_v1beta.py`: Exhaustively probes all Agent/Assistant endpoints.
- **Configuration**:
  - `scripts/inspect_engine.py`: Dumps Engine configuration and attached Data Stores.
  - `scripts/create_dummy_datastore.py`: Creates and links a dummy data store to resolve generic "No Data Store" errors.
  - `scripts/inspect_serving_config.py`: Checks the default search serving config.

## Project Structure

```
.
├── configs/                 # Agent configuration JSONs
├── data/                    # Generated data and golden sets
├── scripts/                 # Utility and Debug scripts
│   ├── create_dummy_datastore.py
│   ├── debug_*.py           # Focused API probes
│   ├── deploy_data_agent.py
│   ├── generate_data.py
│   ├── load_to_bq.py
│   └── ...
├── src/
│   └── orchestrator/        # Core harness logic
│       ├── agent_client.py  # Abstract, Mock, and Real Agent clients
│       ├── engine.py        # Test execution engine
│       └── main.py          # CLI entrypoint
├── results.json             # Test run outputs
├── pyproject.toml           # Project dependencies
└── README.md
```

## Known Issues

- **Search Dominance**: The implicit routing sometimes favors Search over Data Agent SQL generation for generic queries.
- **API Constraints**: `v1beta` `conversations` endpoints may return `400` if the engine has multiple data stores incompatible with certain query specs. The harness currently bypasses this using the `:answer` endpoint.
