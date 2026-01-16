#!/usr/bin/env python3
"""
===============================================================================
DATA INSIGHTS AGENT - EXCEL-BASED TEST HARNESS
===============================================================================

PURPOSE:
    Test a deployed Data Insights Agent by querying it with questions from
    an Excel file and analyzing the responses, including SQL extraction,
    error categorization, and performance metrics.

WHAT THIS SCRIPT DOES:
    1. Reads questions from an Excel file (first column, starting row 2)
    2. Queries the deployed agent via Discovery Engine API
    3. Extracts responses using the same logic as the optimizer:
       - Thoughts (internal reasoning marked with thought=True)
       - Response (natural language answer)
       - Generated SQL (from code blocks or bare SELECT statements)
    4. Categorizes errors and tracks performance metrics
    5. Saves comprehensive results to timestamped JSON file
    6. Provides detailed summary statistics

AUTHENTICATION:
    Uses Google Cloud Application Default Credentials (ADC):
    - Your local gcloud credentials: gcloud auth application-default login
    - Or service account via GOOGLE_APPLICATION_CREDENTIALS env var

TWO TYPES OF AUTHORIZATION:
    1. API Caller Auth (YOU calling the API) - Uses ADC credentials
       ✓ This script handles this automatically
    
    2. Agent Auth (AGENT accessing BigQuery) - Requires OAuth consent
       ✗ Must be completed manually via authorization URL
       If agent returns empty responses, run: python scripts/deployment/authorize_agent.py

SESSION MANAGEMENT:
    By default, each question creates a new session (independent queries).
    Set USE_SAME_SESSION=true in .env for conversational mode where all
    questions share the same session context.

ENVIRONMENT VARIABLES REQUIRED:
    GOOGLE_CLOUD_PROJECT (or PROJECT_ID) - GCP project ID
    DIA_ENGINE_ID (or ENGINE_ID)         - Discovery Engine ID
    DIA_AGENT_ID (or AGENT_ID)          - Agent ID (numeric)
    DIA_LOCATION (or LOCATION)          - Agent location (default: "global")

OPTIONAL ENVIRONMENT VARIABLES:
    USE_SAME_SESSION                     - true/false (default: false)

EXCEL FILE FORMAT:
    - Row 1: Headers (skipped)
    - Row 2+: Questions in Column A
    - Empty cells are automatically skipped

USAGE:
    # Test with default Excel file
    python scripts/test_agent_from_excel.py
    
    # Test with specific Excel file
    python scripts/test_agent_from_excel.py path/to/questions.xlsx
    
    # Use conversational mode (same session)
    export USE_SAME_SESSION=true
    python scripts/test_agent_from_excel.py data/evalset.xlsx

OUTPUT:
    - Excel file: agent_test_results_YYYYMMDD_HHMMSS.xlsx (main output)
    - JSON file: agent_test_results_YYYYMMDD_HHMMSS.json (raw data backup)
    - Contains: questions, responses, SQL, metrics, error categorization in columns
    - Console: Detailed progress and summary statistics

ERROR CATEGORIES:
    - no_sql_generated: Agent responded but no SQL found
    - empty_response: Agent returned no content
    - authorization_required: OAuth authorization needed
    - api_error: API call failed
    - timeout: Request timed out
    - unknown: Uncategorized error

PERFORMANCE METRICS TRACKED:
    - total_time: End-to-end processing time
    - api_response_time: Time for API to respond
    - extraction_time: Time to parse response
    - thought_length: Character count of thoughts
    - response_length: Character count of response
    - sql_length: Character count of SQL

SQL EXTRACTION PATTERNS (in priority order):
    1. Markdown SQL blocks: ```sql ... ```
    2. Code blocks with SELECT: ``` SELECT ... ```
    3. Bare SELECT at line start: SELECT ...

API ENDPOINT USED:
    POST https://{location}-discoveryengine.googleapis.com/v1alpha/
         projects/{project}/locations/{location}/collections/default_collection/
         engines/{engine}/assistants/default_assistant:streamAssist

IMPORTANT NOTES:
    - Agent must be authorized for BigQuery access via OAuth
    - Authorization in Console UI does NOT work for API access
    - Each API caller must complete OAuth separately
    - State parameter in OAuth is binary data (normal, not corrupted)
    - Uses same AgentClient and extraction logic as the optimizer

RELATED SCRIPTS:
    - scripts/deployment/authorize_agent.py - Get OAuth authorization URL
    - src/evaluation/runner.py - Optimizer's TestRunner (same extraction logic)
    - src/evaluation/agent_client.py - API client with retry logic

TROUBLESHOOTING:
    Empty responses (0 chars)?
        → Agent needs OAuth authorization
        → Run: python scripts/deployment/authorize_agent.py
        → Click the URL and complete OAuth flow
    
    404 on OAuth callback?
        → Known v1alpha API issue
        → Report to Google Cloud Support
    
    "Missing environment variables"?
        → Check your .env file has required variables
        → See ENV_SETUP.md for details

===============================================================================
"""

import os
import sys
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from dotenv import load_dotenv

# Add src to path to import AgentClient
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from evaluation.agent_client import AgentClient, AgentAuthorizationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def categorize_error(result: Dict[str, Any]) -> str:
    """
    Categorize the type of error or issue with the agent response.
    
    Error Categories:
        - no_sql_generated: Agent responded but no SQL was extracted
        - empty_response: Agent returned no content (likely needs authorization)
        - authorization_required: Explicit authorization error (403)
        - api_error: API call failed with error
        - timeout: Request timed out
        - unknown: Uncategorized error
    
    Args:
        result: Result dictionary from agent query
        
    Returns:
        Error category string
    """
    status = result.get("status")
    
    # Check for explicit authorization error
    if status == "auth_error":
        return "authorization_required"
    
    # Check for general API errors
    if status == "error":
        error_msg = result.get("error", "").lower()
        if "timeout" in error_msg:
            return "timeout"
        return "api_error"
    
    # Check for successful API call but problematic response
    if status == "success":
        response = result.get("response", {})
        
        # Check if response is completely empty (likely authorization issue)
        if not response.get("response") and not response.get("thoughts"):
            # Check raw messages for authorization requirement
            raw_messages = response.get("raw_messages", [])
            for msg in raw_messages:
                if "answer" in msg and "requiredAuthorizations" in msg.get("answer", {}):
                    return "authorization_required"
            return "empty_response"
        
        # Check if SQL was not generated
        if not response.get("generated_sql"):
            return "no_sql_generated"
    
    return "unknown"


def calculate_performance_metrics(
    start_time: float,
    api_start: float,
    api_end: float,
    extraction_start: float,
    extraction_end: float,
    response_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate performance metrics for the agent query.
    
    Metrics Tracked:
        - total_time: Total processing time (seconds)
        - api_response_time: Time waiting for API response (seconds)
        - extraction_time: Time parsing/extracting response (seconds)
        - thought_length: Character count of internal reasoning
        - response_length: Character count of user-facing response
        - sql_length: Character count of generated SQL
        - tokens_estimate: Rough estimate of tokens (chars / 4)
    
    Args:
        start_time: Overall start timestamp
        api_start: API call start timestamp
        api_end: API call end timestamp
        extraction_start: Extraction start timestamp
        extraction_end: Extraction end timestamp
        response_data: Extracted response data
        
    Returns:
        Dictionary of performance metrics
    """
    total_time = time.time() - start_time
    api_time = api_end - api_start
    extraction_time = extraction_end - extraction_start
    
    thoughts = response_data.get("thoughts", "")
    response = response_data.get("response", "")
    sql = response_data.get("generated_sql", "")
    
    return {
        "total_time": round(total_time, 3),
        "api_response_time": round(api_time, 3),
        "extraction_time": round(extraction_time, 3),
        "thought_length": len(thoughts),
        "response_length": len(response),
        "sql_length": len(sql),
        "tokens_estimate": (len(thoughts) + len(response) + len(sql)) // 4
    }


def extract_agent_response(streaming_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract the agent's response from the streaming messages format.
    Uses the same logic as TestRunner.parse_response() to properly extract
    thoughts, responses, and SQL queries.
    
    Response Structure from API:
        [
          {
            "answer": {
              "replies": [
                {
                  "groundedContent": {
                    "content": {
                      "text": "...",
                      "thought": true/false
                    }
                  }
                }
              ]
            }
          },
          {
            "sessionInfo": {
              "session": "projects/.../sessions/123"
            }
          }
        ]
    
    Args:
        streaming_messages: List of streaming message chunks from streamAssist API
        
    Returns:
        Dictionary containing extracted response data including:
        - thoughts: Internal reasoning (marked with thought=True)
        - response: Natural language answer to user
        - generated_sql: Extracted SQL query
        - session_info: Session metadata
        - session_id: Extracted session ID
        - raw_messages: Original streaming messages
    """
    import re
    
    thoughts = []
    response_parts = []
    session_info = None
    session_id = None
    
    # Extract from streaming messages using groundedContent structure
    for message in streaming_messages:
        # Extract from answer.replies with groundedContent
        if "answer" in message and "replies" in message["answer"]:
            for reply in message["answer"]["replies"]:
                # Look for groundedContent structure (used by optimizer)
                if "groundedContent" in reply:
                    content = reply["groundedContent"].get("content", {})
                    text = content.get("text", "")
                    is_thought = content.get("thought", False)
                    
                    if is_thought:
                        thoughts.append(text)
                    else:
                        response_parts.append(text)
                # FALLBACK: Look for simple reply field
                elif "reply" in reply:
                    response_parts.append(reply["reply"])
        
        # Extract session info
        if "sessionInfo" in message:
            session_info = message["sessionInfo"]
            if "session" in session_info:
                session_id = session_info["session"]
    
    full_thoughts = "".join(thoughts).strip()
    full_response = "".join(response_parts).strip()
    
    # Extract SQL using the same logic as TestRunner._extract_sql_string()
    # Try response first, then thoughts
    generated_sql = _extract_sql_string(full_response)
    if not generated_sql:
        generated_sql = _extract_sql_string(full_thoughts)
    
    return {
        "thoughts": full_thoughts,
        "response": full_response,
        "generated_sql": generated_sql,
        "session_info": session_info,
        "session_id": session_id,
        "raw_messages": streaming_messages
    }


def _extract_sql_string(text: str) -> str:
    """
    Extract SQL query from text using multiple patterns.
    Same logic as TestRunner._extract_sql_string().
    
    Extraction Priority:
        1. Markdown SQL blocks: ```sql ... ```
        2. Code blocks with SELECT: ``` SELECT ... ```
        3. Bare SELECT at line start
    
    Args:
        text: Text to search for SQL
        
    Returns:
        Extracted SQL query or empty string
    """
    import re
    
    # Look for markdown sql block (```sql ... ```)
    match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Look for generic code block if it starts with SELECT
    match = re.search(r"```\s*(SELECT.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Look for bare SELECT statement at start of line
    match = re.search(r"(?m)^(SELECT\s+.*)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return ""


def read_questions_from_excel(excel_path: str) -> List[str]:
    """
    Read questions from the first column of an Excel file (starting from row 2).
    
    Excel Format:
        Row 1: Header (skipped)
        Row 2+: Questions in Column A
        Empty cells are automatically filtered out
    
    Args:
        excel_path: Path to the Excel file
        
    Returns:
        List of questions (as strings)
    """
    logger.info(f"Reading questions from: {excel_path}")
    
    # Read Excel file (will read first sheet by default)
    df = pd.read_excel(excel_path)
    
    # Get first column, skip header (row 0), and remove any NaN values
    questions = df.iloc[1:, 0].dropna().tolist()
    
    # Convert to strings and strip whitespace
    questions = [str(q).strip() for q in questions if str(q).strip()]
    
    logger.info(f"Found {len(questions)} questions")
    return questions


def test_agent_with_questions(
    excel_path: str,
    project_id: str,
    location: str,
    engine_id: str,
    agent_id: str,
    output_file: str = None,
    use_same_session: bool = False
) -> List[Dict[str, Any]]:
    """
    Test agent by querying with questions from Excel file.
    
    Process:
        1. Read questions from Excel
        2. Initialize AgentClient with connection pooling
        3. For each question:
           a. Query agent via streamAssist API
           b. Extract response (thoughts, answer, SQL)
           c. Categorize any errors
           d. Calculate performance metrics
           e. Log progress
        4. Save results to JSON file
        5. Print summary statistics
    
    Args:
        excel_path: Path to Excel file with questions
        project_id: Google Cloud project ID
        location: Agent location (e.g., "global", "us")
        engine_id: Discovery Engine ID
        agent_id: Agent ID (numeric)
        output_file: Optional path to save results JSON
        use_same_session: If True, all questions use the same session (conversation context)
                         If False (default), each question creates a new session
        
    Returns:
        List of result dictionaries with questions, responses, metrics, and error categories
    """
    # Read questions
    questions = read_questions_from_excel(excel_path)
    
    if not questions:
        logger.error("No questions found in Excel file")
        return []
    
    # Initialize agent client
    logger.info(f"Initializing agent client for agent: {agent_id}")
    client = AgentClient(
        project_id=project_id,
        location=location,
        engine_id=engine_id,
        agent_id=agent_id
    )
    
    # Process each question
    results = []
    current_session_id = None  # Track session across questions if needed
    
    for idx, question in enumerate(questions, start=1):
        logger.info(f"\n{'='*80}")
        logger.info(f"Question {idx}/{len(questions)}: {question}")
        if use_same_session and current_session_id:
            logger.info(f"Using existing session: ...{current_session_id[-20:]}")
        logger.info(f"{'='*80}")
        
        # Initialize result structure
        result = {
            "question_number": idx,
            "question": question,
            "timestamp": datetime.now().isoformat(),
            "status": "pending",
            "response": None,
            "error": None,
            "error_category": None,
            "metrics": None,
            "session_id": current_session_id
        }
        
        # Start timing
        start_time = time.time()
        
        try:
            # Query the agent (with session if use_same_session=True)
            api_start = time.time()
            if use_same_session and current_session_id:
                streaming_messages = client.query_agent(text=question, session_id=current_session_id)
            else:
                streaming_messages = client.query_agent(text=question)
            api_end = time.time()
            
            # Extract response data using proper groundedContent parsing
            extraction_start = time.time()
            response_data = extract_agent_response(streaming_messages)
            extraction_end = time.time()
            
            # Calculate performance metrics
            metrics = calculate_performance_metrics(
                start_time, api_start, api_end,
                extraction_start, extraction_end,
                response_data
            )
            
            # Update session tracking
            if use_same_session and response_data["session_id"]:
                current_session_id = response_data["session_id"]
                result["session_id"] = current_session_id
            
            result["status"] = "success"
            result["response"] = response_data
            result["metrics"] = metrics
            
            # Categorize any issues
            result["error_category"] = categorize_error(result)
            
            # Log response summary
            logger.info(f"✓ Response received")
            logger.info(f"  Response: {len(response_data['response'])} chars")
            if response_data["thoughts"]:
                logger.info(f"  Thoughts: {len(response_data['thoughts'])} chars")
            if response_data["generated_sql"]:
                logger.info(f"  Generated SQL: {len(response_data['generated_sql'])} chars")
                # Show first line of SQL
                first_line = response_data["generated_sql"].split('\n')[0]
                logger.info(f"    {first_line}...")
            else:
                logger.warning(f"  ⚠️  No SQL found in response")
            
            # Log performance
            logger.info(f"  Performance: {metrics['api_response_time']:.2f}s API, "
                       f"{metrics['total_time']:.2f}s total")
            
            # Log error category if not successful
            if result["error_category"] != "unknown":
                logger.warning(f"  Issue: {result['error_category']}")
            
            # Print first 200 chars of response
            preview = response_data["response"][:200]
            if len(response_data["response"]) > 200:
                preview += "..."
            if preview:
                logger.info(f"  Preview: {preview}")
            
        except AgentAuthorizationError as e:
            logger.error(f"✗ Authorization error: {e}")
            logger.error(f"  Please run: python scripts/deployment/authorize_agent.py")
            result["status"] = "auth_error"
            result["error"] = str(e)
            result["error_category"] = "authorization_required"
            result["metrics"] = {
                "total_time": round(time.time() - start_time, 3),
                "api_response_time": 0,
                "extraction_time": 0,
                "thought_length": 0,
                "response_length": 0,
                "sql_length": 0,
                "tokens_estimate": 0
            }
            
        except Exception as e:
            logger.error(f"✗ Error querying agent: {e}")
            result["status"] = "error"
            result["error"] = str(e)
            result["error_category"] = "api_error"
            result["metrics"] = {
                "total_time": round(time.time() - start_time, 3),
                "api_response_time": 0,
                "extraction_time": 0,
                "thought_length": 0,
                "response_length": 0,
                "sql_length": 0,
                "tokens_estimate": 0
            }
        
        results.append(result)
    
    # Save results to both JSON and Excel
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file_base = f"agent_test_results_{timestamp}"
        json_file = f"{output_file_base}.json"
        excel_file = f"{output_file_base}.xlsx"
    else:
        # User provided output file - create both JSON and Excel versions
        base = output_file.rsplit('.', 1)[0]
        json_file = f"{base}.json"
        excel_file = f"{base}.xlsx"
    
    logger.info(f"\n{'='*80}")
    logger.info(f"Saving results...")
    
    # Save JSON (with full raw data)
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"  JSON: {json_file}")
    
    # Save Excel (structured tabular format)
    save_results_to_excel(results, excel_file)
    logger.info(f"  Excel: {excel_file}")
    
    # Print summary statistics
    print_summary(results, use_same_session, excel_file, json_file)
    
    return results


def save_results_to_excel(results: List[Dict[str, Any]], excel_file: str):
    """
    Save test results to Excel file with all data in separate columns.
    
    Excel Structure:
        - One row per question
        - Columns for all extracted data and metrics
        - Easy to filter, sort, and analyze
    
    Args:
        results: List of test results
        excel_file: Path to save Excel file
    """
    # Prepare data for DataFrame
    rows = []
    
    for result in results:
        response = result.get("response", {})
        metrics = result.get("metrics", {})
        
        row = {
            # Basic info
            "Question Number": result.get("question_number"),
            "Question": result.get("question"),
            "Timestamp": result.get("timestamp"),
            "Status": result.get("status"),
            "Error Category": result.get("error_category"),
            
            # Response data
            "Response (Natural Language)": response.get("response", ""),
            "Thoughts (Internal Reasoning)": response.get("thoughts", ""),
            "Generated SQL": response.get("generated_sql", ""),
            
            # Performance metrics
            "Total Time (s)": metrics.get("total_time", 0),
            "API Response Time (s)": metrics.get("api_response_time", 0),
            "Extraction Time (s)": metrics.get("extraction_time", 0),
            "Response Length (chars)": metrics.get("response_length", 0),
            "Thoughts Length (chars)": metrics.get("thought_length", 0),
            "SQL Length (chars)": metrics.get("sql_length", 0),
            "Tokens Estimate": metrics.get("tokens_estimate", 0),
            
            # Session info
            "Session ID": result.get("session_id", ""),
            
            # Error info (if any)
            "Error Message": result.get("error", "")
        }
        
        rows.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Save to Excel with formatting
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Test Results', index=False)
        
        # Get the workbook and worksheet
        workbook = writer.book
        worksheet = writer.sheets['Test Results']
        
        # Adjust column widths for readability
        column_widths = {
            'A': 15,  # Question Number
            'B': 60,  # Question
            'C': 20,  # Timestamp
            'D': 12,  # Status
            'E': 25,  # Error Category
            'F': 80,  # Response
            'G': 80,  # Thoughts
            'H': 100, # SQL
            'I': 15,  # Total Time
            'J': 18,  # API Response Time
            'K': 18,  # Extraction Time
            'L': 20,  # Response Length
            'M': 20,  # Thoughts Length
            'N': 18,  # SQL Length
            'O': 15,  # Tokens Estimate
            'P': 40,  # Session ID
            'Q': 60   # Error Message
        }
        
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width
        
        # Enable text wrap for long text columns
        from openpyxl.styles import Alignment
        for row in worksheet.iter_rows(min_row=2, max_row=len(rows)+1):
            for cell in row:
                if cell.column_letter in ['B', 'F', 'G', 'H', 'Q']:  # Question, Response, Thoughts, SQL, Error
                    cell.alignment = Alignment(wrap_text=True, vertical='top')


def print_summary(results: List[Dict[str, Any]], use_same_session: bool, excel_file: str, json_file: str):
    """
    Print comprehensive summary statistics.
    
    Summary Includes:
        - Total questions tested
        - Success/error counts
        - SQL extraction rate
        - Error categorization breakdown
        - Performance statistics (avg, min, max)
        - Session mode
    
    Args:
        results: List of test results
        use_same_session: Whether single session mode was used
        excel_file: Path to saved Excel file
        json_file: Path to saved JSON file
    """
    total = len(results)
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] in ["error", "auth_error"])
    
    sql_found_count = sum(
        1 for r in results 
        if r["status"] == "success" and r["response"] and r["response"]["generated_sql"]
    )
    
    # Error categorization breakdown
    error_categories = {}
    for r in results:
        cat = r.get("error_category", "unknown")
        error_categories[cat] = error_categories.get(cat, 0) + 1
    
    # Performance statistics
    api_times = [r["metrics"]["api_response_time"] for r in results if r.get("metrics")]
    total_times = [r["metrics"]["total_time"] for r in results if r.get("metrics")]
    
    avg_api_time = sum(api_times) / len(api_times) if api_times else 0
    avg_total_time = sum(total_times) / len(total_times) if total_times else 0
    min_api_time = min(api_times) if api_times else 0
    max_api_time = max(api_times) if api_times else 0
    
    logger.info(f"\n{'='*80}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Total questions: {total}")
    logger.info(f"Successful: {success_count} ({success_count/max(total,1)*100:.1f}%)")
    logger.info(f"Errors: {error_count}")
    logger.info(f"SQL extracted: {sql_found_count}/{success_count}")
    
    logger.info(f"\nError Categorization:")
    for category, count in sorted(error_categories.items()):
        logger.info(f"  {category}: {count}")
    
    logger.info(f"\nPerformance Metrics:")
    logger.info(f"  Avg API response time: {avg_api_time:.2f}s")
    logger.info(f"  Avg total time: {avg_total_time:.2f}s")
    logger.info(f"  Min/Max API time: {min_api_time:.2f}s / {max_api_time:.2f}s")
    
    if use_same_session:
        logger.info(f"\nSession mode: Single session (conversational)")
    else:
        logger.info(f"\nSession mode: New session per question")
    
    logger.info(f"\nResults saved to:")
    logger.info(f"  Excel: {excel_file}")
    logger.info(f"  JSON: {json_file}")
    logger.info(f"{'='*80}")


def main():
    """
    Main entry point.
    
    Environment Setup:
        - Loads .env file if present
        - Validates required environment variables
        - Sets defaults for optional variables
    
    Command Line:
        python scripts/test_agent_from_excel.py [excel_file_path]
        
        If no path provided, uses default:
        "Gemini Evaluation Questions _ With Screenshots.xlsx"
    
    Exit Codes:
        0 - Success
        1 - Error (missing env vars, file not found, or test failure)
    """
    # Load environment variables
    load_dotenv()
    
    # Get required environment variables (matching project convention)
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    location = os.getenv("DIA_LOCATION") or os.getenv("LOCATION", "global")
    engine_id = os.getenv("DIA_ENGINE_ID") or os.getenv("ENGINE_ID")
    agent_id = os.getenv("DIA_AGENT_ID") or os.getenv("AGENT_ID")
    
    # Optional: Use same session for all questions (conversational mode)
    # Default is False (each question gets a new session)
    use_same_session = os.getenv("USE_SAME_SESSION", "false").lower() in ["true", "1", "yes"]
    
    # Validate required variables
    missing_vars = []
    if not project_id:
        missing_vars.append("GOOGLE_CLOUD_PROJECT (or PROJECT_ID)")
    if not engine_id:
        missing_vars.append("DIA_ENGINE_ID (or ENGINE_ID)")
    if not agent_id:
        missing_vars.append("DIA_AGENT_ID (or AGENT_ID)")
    
    if missing_vars:
        logger.error("Missing required environment variables:")
        for var in missing_vars:
            logger.error(f"  - {var}")
        logger.error("\nPlease add these to your .env file")
        logger.error("See script header for documentation on required variables")
        sys.exit(1)
    
    # Get Excel file path from command line or use default
    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    else:
        # Default to the Gemini Evaluation Questions file
        excel_path = "Gemini Evaluation Questions _ With Screenshots.xlsx"
    
    if not os.path.exists(excel_path):
        logger.error(f"Excel file not found: {excel_path}")
        logger.error("Usage: python scripts/test_agent_from_excel.py [path/to/questions.xlsx]")
        sys.exit(1)
    
    logger.info(f"Configuration:")
    logger.info(f"  Project: {project_id}")
    logger.info(f"  Location: {location}")
    logger.info(f"  Engine: {engine_id}")
    logger.info(f"  Agent: {agent_id}")
    logger.info(f"  Session mode: {'Single session (conversational)' if use_same_session else 'New session per question'}")
    logger.info(f"  Excel file: {excel_path}")
    
    # Run the test
    try:
        results = test_agent_with_questions(
            excel_path=excel_path,
            project_id=project_id,
            location=location,
            engine_id=engine_id,
            agent_id=agent_id,
            use_same_session=use_same_session
        )
        
        if not results:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.warning("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
