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
    2. Queries the deployed agent via Discovery Engine API (3-minute timeout per question)
    3. Extracts responses using the same logic as the optimizer:
       - Thoughts (internal reasoning marked with thought=True)
       - Response (natural language answer)
       - Generated SQL (from code blocks or bare SELECT statements)
    4. Categorizes errors and tracks performance metrics
    5. Saves results INCREMENTALLY after each question (survives interruptions!)
    6. Auto-stops after 3 consecutive timeouts (circuit breaker)
    7. Provides detailed summary statistics

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
    
    # Test with more parallel workers
    python scripts/test_agent_from_excel.py data/evalset.xlsx --max-workers 20
    
    # Retest only failures from previous run (timeouts, api errors, etc.)
    python scripts/test_agent_from_excel.py --retest-from agent_test_results_20260120_224454.json
    
    # Retest with automatic recursive retries (2 iterations)
    python scripts/test_agent_from_excel.py --retest-from results.json --recurse 2
    
    # Retest with 3 automatic iterations (keeps retrying failures)
    python scripts/test_agent_from_excel.py --retest-from results.json --recurse 3
    
    # Use conversational mode (same session)
    export USE_SAME_SESSION=true
    python scripts/test_agent_from_excel.py data/evalset.xlsx

OUTPUT:
    - Excel file: agent_test_results_YYYYMMDD_HHMMSS.xlsx (main output)
    - JSON file: agent_test_results_YYYYMMDD_HHMMSS.json (raw data backup)
    - Retest files: original_name_retest_N.{json,xlsx} (when using --retest-from)
    - Contains: questions, responses, SQL, metrics, error categorization in columns
    - Console: Detailed progress and summary statistics

RETEST FUNCTIONALITY:
    - Use --retest-from to retest only failures from a previous run
    - Automatically retests: timeout, api_error, authorization_required, empty_response
    - Skips: no_sql_generated (agent responded), success (SQL generated)
    - Generates new files with _retest_N suffix (preserves original, increments cleanly)
    - Use --recurse N to automatically run N retest iterations
    - Example single retest: python scripts/test_agent_from_excel.py --retest-from results.json
    - Example recursive: python scripts/test_agent_from_excel.py --retest-from results.json --recurse 3
    - Naming: base_retest_1.json → base_retest_2.json → base_retest_3.json (clean increment)

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
    
    Request timing out (3 min+)?
        → Script auto-times out after 3 minutes per question
        → Saves progress and moves to next question
        → After 3 consecutive timeouts, execution stops automatically
    
    Script interrupted or crashed?
        → No problem! Results are saved after each question
        → Check the timestamped output files for partial results
    
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
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import random

# Add src to path to import AgentClient
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from evaluation.agent_client import AgentClient, AgentAuthorizationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def categorize_error(result: Dict[str, Any]) -> Optional[str]:
    """
    Categorize the type of error or issue with the agent response.
    
    Error Categories:
        - no_sql_generated: Agent responded but no SQL was extracted
        - empty_response: Agent returned no content (likely needs authorization)
        - authorization_required: Explicit authorization error (403)
        - api_error: API call failed with error
        - timeout: Request timed out
        - None: Success - SQL was successfully generated
    
    Args:
        result: Result dictionary from agent query
        
    Returns:
        Error category string or None for success
    """
    status = result.get("status")
    
    # Check for explicit timeout error
    if status == "timeout":
        return "timeout"
    
    # Check for explicit authorization error
    if status == "auth_error":
        return "authorization_required"
    
    # Check for general API errors
    if status == "error":
        error_msg = result.get("error", "").lower()
        if "timeout" in error_msg or "timed out" in error_msg:
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
        
        # Success - SQL was generated
        return None
    
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


def _process_questions_parallel(
    client: AgentClient,
    questions: List[str],
    max_workers: int,
    json_file: str,
    excel_file: str,
    timeout_seconds: int
) -> List[Dict[str, Any]]:
    """
    Process questions in parallel using ThreadPoolExecutor.
    
    Args:
        client: AgentClient instance
        questions: List of questions to process
        max_workers: Maximum number of parallel workers
        json_file: Path to save JSON results
        excel_file: Path to save Excel results
        timeout_seconds: Timeout per question
        
    Returns:
        List of results
    """
    total_questions = len(questions)
    results = []
    results_lock = threading.Lock()
    completed = 0
    
    logger.info(f"Executing {total_questions} questions with {max_workers} parallel workers...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all questions
        future_to_question = {
            executor.submit(
                _run_single_question,
                client, question, idx, total_questions,
                None, False, timeout_seconds
            ): (question, idx)
            for idx, question in enumerate(questions, start=1)
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_question):
            question, idx = future_to_question[future]
            try:
                result = future.result()
                with results_lock:
                    results.append(result)
                    completed += 1
                    
                    # Incremental save every 5 questions or on completion
                    if completed % 5 == 0 or completed == total_questions:
                        # Sort results by question_number for consistent output
                        sorted_results = sorted(results, key=lambda r: r['question_number'])
                        try:
                            with open(json_file, 'w') as f:
                                json.dump(sorted_results, f, indent=2)
                            save_results_to_excel(sorted_results, excel_file)
                            logger.info(f"💾 Progress saved: {completed}/{total_questions} ({completed*100//total_questions}%)")
                        except Exception as e:
                            logger.warning(f"Failed to save progress: {e}")
                
            except Exception as e:
                logger.error(f"Error processing question '{question[:60]}...': {e}")
                with results_lock:
                    results.append({
                        "question_number": idx,
                        "question": question,
                        "timestamp": datetime.now().isoformat(),
                        "status": "error",
                        "error": str(e),
                        "error_category": "api_error",
                        "metrics": None,
                        "response": None
                    })
                    completed += 1
    
    # Sort final results
    results.sort(key=lambda r: r['question_number'])
    logger.info(f"\n✓ All {total_questions} questions completed\n")
    
    return results


def _process_questions_sequential(
    client: AgentClient,
    questions: List[str],
    json_file: str,
    excel_file: str,
    timeout_seconds: int
) -> List[Dict[str, Any]]:
    """
    Process questions sequentially (required for use_same_session=True).
    
    Args:
        client: AgentClient instance
        questions: List of questions to process
        json_file: Path to save JSON results
        excel_file: Path to save Excel results
        timeout_seconds: Timeout per question
        
    Returns:
        List of results
    """
    results = []
    current_session_id = None
    consecutive_timeouts = 0
    MAX_CONSECUTIVE_TIMEOUTS = 3
    total_questions = len(questions)
    
    for idx, question in enumerate(questions, start=1):
        # Run single question
        result = _run_single_question(
            client, question, idx, total_questions,
            current_session_id, use_same_session=True, timeout_seconds=timeout_seconds
        )
        
        # Update session tracking
        if result.get("response") and result["response"].get("session_id"):
            current_session_id = result["response"]["session_id"]
        
        # Track timeouts
        if result["status"] == "timeout":
            consecutive_timeouts += 1
            if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                logger.error(f"\nSTOPPING: {MAX_CONSECUTIVE_TIMEOUTS} consecutive timeouts detected")
                logger.error(f"Processed {idx} out of {total_questions} questions")
                results.append(result)
                # Save partial results
                with open(json_file, 'w') as f:
                    json.dump(results, f, indent=2)
                save_results_to_excel(results, excel_file)
                return results
        else:
            consecutive_timeouts = 0
        
        results.append(result)
        
        # Incremental save
        if idx % 5 == 0 or idx == total_questions:
            try:
                with open(json_file, 'w') as f:
                    json.dump(results, f, indent=2)
                save_results_to_excel(results, excel_file)
                logger.info(f"💾 Progress saved: {idx}/{total_questions}")
            except Exception as e:
                logger.warning(f"Failed to save progress: {e}")
    
    return results


def _run_single_question(
    client: AgentClient,
    question: str,
    question_idx: int,
    total_questions: int,
    current_session_id: Optional[str] = None,
    use_same_session: bool = False,
    timeout_seconds: int = 180
) -> Dict[str, Any]:
    """
    Run a single question query with isolated session (for parallel execution).
    
    Args:
        client: AgentClient instance
        question: Question text to query
        question_idx: Index of question (1-based)
        total_questions: Total number of questions
        current_session_id: Optional session ID for conversational mode
        use_same_session: Whether to use existing session
        timeout_seconds: Timeout in seconds (default: 180)
        
    Returns:
        Dict with test result including response, metrics, and error info
    """
    # Add small random delay to avoid overwhelming agent
    query_delay = random.uniform(0.1, 0.5)
    time.sleep(query_delay)
    
    logger.info(f"[{question_idx}/{total_questions}] Processing: {question[:60]}...")
    
    # Initialize result structure
    result = {
        "question_number": question_idx,
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
        # Query the agent
        api_start = time.time()
        if use_same_session and current_session_id:
            streaming_messages = client.query_agent(
                text=question,
                session_id=current_session_id,
                timeout=timeout_seconds
            )
        else:
            streaming_messages = client.query_agent(
                text=question,
                timeout=timeout_seconds
            )
        api_end = time.time()
        
        # Extract response data
        extraction_start = time.time()
        response_data = extract_agent_response(streaming_messages)
        extraction_end = time.time()
        
        # Calculate performance metrics
        metrics = calculate_performance_metrics(
            start_time, api_start, api_end,
            extraction_start, extraction_end,
            response_data
        )
        
        result["status"] = "success"
        result["response"] = response_data
        result["metrics"] = metrics
        result["session_id"] = response_data.get("session_id", current_session_id)
        
        # Categorize any issues
        result["error_category"] = categorize_error(result)
        
        # Log response summary
        logger.info(f"[{question_idx}/{total_questions}] ✓ Response: {len(response_data['response'])} chars, "
                   f"SQL: {'Yes' if response_data['generated_sql'] else 'No'}, "
                   f"Time: {metrics['api_response_time']:.2f}s")
        
    except requests.Timeout as e:
        logger.error(f"[{question_idx}/{total_questions}] ✗ Timeout after {timeout_seconds}s")
        result["status"] = "timeout"
        result["error"] = f"Request timed out after {timeout_seconds} seconds"
        result["error_category"] = "timeout"
        result["metrics"] = {
            "total_time": round(time.time() - start_time, 3),
            "api_response_time": 0,
            "extraction_time": 0,
            "thought_length": 0,
            "response_length": 0,
            "sql_length": 0,
            "tokens_estimate": 0
        }
        
    except AgentAuthorizationError as e:
        logger.error(f"[{question_idx}/{total_questions}] ✗ Authorization error")
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
        logger.error(f"[{question_idx}/{total_questions}] ✗ Error: {type(e).__name__}")
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
    
    return result


def test_agent_with_questions(
    excel_path: str,
    project_id: str,
    location: str,
    engine_id: str,
    agent_id: str,
    output_file: str = None,
    use_same_session: bool = False,
    max_workers: int = 10
) -> List[Dict[str, Any]]:
    """
    Test agent by querying with questions from Excel file IN PARALLEL.
    
    Process:
        1. Read questions from Excel
        2. Initialize AgentClient with connection pooling
        3. Execute questions in parallel using ThreadPoolExecutor:
           a. Query agent via streamAssist API
           b. Extract response (thoughts, answer, SQL)
           c. Categorize any errors
           d. Calculate performance metrics
           e. Log progress
        4. Save results incrementally to JSON/Excel files
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
        max_workers: Maximum number of parallel workers (default: 10)
        
    Returns:
        List of result dictionaries with questions, responses, metrics, and error categories
    """
    # Read questions
    questions = read_questions_from_excel(excel_path)
    
    if not questions:
        logger.error("No questions found in Excel file")
        return []
    
    # Initialize agent client with connection pool sized for parallel workers
    logger.info(f"Initializing agent client for agent: {agent_id}")
    max_connections = max(100, max_workers + 20)
    client = AgentClient(
        project_id=project_id,
        location=location,
        engine_id=engine_id,
        agent_id=agent_id,
        max_connections=max_connections
    )
    
    # Set up output files for incremental saving
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
    
    logger.info(f"\nResults will be saved incrementally to:")
    logger.info(f"  JSON: {json_file}")
    logger.info(f"  Excel: {excel_file}")
    logger.info(f"  Max Workers: {max_workers}")
    logger.info(f"  Parallel Mode: {'DISABLED (same session)' if use_same_session else 'ENABLED'}")
    
    # PARALLEL vs SEQUENTIAL mode
    TIMEOUT_SECONDS = 180  # 3 minutes per question
    
    if use_same_session:
        # SEQUENTIAL MODE: Required for conversational context
        logger.warning(f"\n⚠️  Running in SEQUENTIAL mode (use_same_session=True)")
        logger.warning(f"   Parallel execution disabled to maintain session context\n")
        results = _process_questions_sequential(
            client, questions, json_file, excel_file, TIMEOUT_SECONDS
        )
    else:
        # PARALLEL MODE: Fast execution for independent questions
        logger.info(f"\n{'='*80}")
        logger.info(f"RUNNING {len(questions)} QUESTIONS IN PARALLEL")
        logger.info(f"{'='*80}\n")
        results = _process_questions_parallel(
            client, questions, max_workers, json_file, excel_file, TIMEOUT_SECONDS
        )
    
    # Final save to ensure everything is persisted
    logger.info(f"\n{'='*80}")
    logger.info(f"Test completed - finalizing results...")
    
    try:
        # Final save (should already be done incrementally, but ensure it's complete)
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2)
        save_results_to_excel(results, excel_file)
        logger.info(f"  ✓ Final results saved")
    except Exception as e:
        logger.error(f"  ✗ Error saving final results: {e}")
    
    # Print summary statistics
    print_summary(results, use_same_session, excel_file, json_file)
    
    return results


def save_results_to_excel(results: List[Dict[str, Any]], excel_file: str):
    """
    Save test results to Excel file with selected columns.
    
    Excel Structure:
        - One row per question
        - Columns: Question, Timestamp, Status, Error Category, Generated SQL, Response, Total Time
    
    Args:
        results: List of test results
        excel_file: Path to save Excel file
    """
    # Prepare data for DataFrame
    rows = []
    
    for result in results:
        response = result.get("response", {})
        metrics = result.get("metrics", {})
        
        # Handle None response (for errors/timeouts)
        response_text = ""
        generated_sql = ""
        if response and isinstance(response, dict):
            response_text = response.get("response", "")
            generated_sql = response.get("generated_sql", "")
        
        # Clean up error category: null instead of "unknown" for successful SQL generation
        error_category = result.get("error_category")
        if error_category == "unknown":
            error_category = None
        
        row = {
            "Question": result.get("question"),
            "Timestamp": result.get("timestamp"),
            "Status": result.get("status"),
            "Error Category": error_category,
            "Generated SQL": generated_sql,
            "Response (Natural Language)": response_text,
            "Total Time (s)": metrics.get("total_time", 0) if metrics else 0,
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
            'A': 60,  # Question
            'B': 20,  # Timestamp
            'C': 12,  # Status
            'D': 25,  # Error Category
            'E': 80,  # Generated SQL
            'F': 80,  # Response
            'G': 15,  # Total Time
        }
        
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width
        
        # Enable text wrap for long text columns
        from openpyxl.styles import Alignment
        for row in worksheet.iter_rows(min_row=2, max_row=len(rows)+1):
            for cell in row:
                if cell.column_letter in ['A', 'E', 'F']:  # Question, Generated SQL, Response
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


def load_previous_results(json_file: str) -> List[Dict[str, Any]]:
    """
    Load previous test results from JSON file.
    
    Args:
        json_file: Path to previous results JSON file
        
    Returns:
        List of previous results
    """
    with open(json_file, 'r') as f:
        return json.load(f)


def identify_retest_questions(
    previous_results: List[Dict[str, Any]],
    exclude_categories: List[str] = None
) -> List[str]:
    """
    Identify questions that need retesting based on error categories.
    
    By default, excludes questions with:
    - None (successful SQL generation)
    - "no_sql_generated" (agent responded but no SQL - not a failure)
    
    Retests:
    - "timeout"
    - "api_error"
    - "authorization_required"
    - "empty_response"
    - "unknown" (unexpected errors)
    
    Args:
        previous_results: List of previous test results
        exclude_categories: Categories to exclude from retest (default: [None, "no_sql_generated"])
        
    Returns:
        List of questions to retest
    """
    if exclude_categories is None:
        exclude_categories = [None, "no_sql_generated"]
    
    retest_questions = []
    for result in previous_results:
        error_category = result.get("error_category")
        question = result.get("question")
        
        # Retest if error_category is not in exclude list and question exists
        if error_category not in exclude_categories and question:
            retest_questions.append(question)
    
    return retest_questions


def merge_results(
    previous_results: List[Dict[str, Any]],
    new_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Merge new retest results with previous results.
    
    For each question:
    - If retested, use new result
    - If not retested, keep original result
    
    Args:
        previous_results: Original test results
        new_results: New retest results
        
    Returns:
        Merged results list maintaining original order
    """
    # Create a map of question -> new result
    new_results_map = {r.get("question"): r for r in new_results}
    
    # Merge results
    merged = []
    for prev_result in previous_results:
        question = prev_result.get("question")
        
        # Use new result if available, otherwise keep previous
        if question in new_results_map:
            # Keep question_number from original
            new_result = new_results_map[question].copy()
            new_result["question_number"] = prev_result.get("question_number")
            merged.append(new_result)
        else:
            merged.append(prev_result)
    
    return merged


def print_retest_summary(
    previous_results: List[Dict[str, Any]],
    new_results: List[Dict[str, Any]],
    merged_results: List[Dict[str, Any]],
    excel_file: str,
    json_file: str
):
    """
    Print summary of retest results comparing before/after.
    
    Args:
        previous_results: Original results
        new_results: New retest results
        merged_results: Merged final results
        excel_file: Path to output Excel file
        json_file: Path to output JSON file
    """
    # Count improvements by category
    improvements = {}
    still_failing = {}
    
    new_results_map = {r.get("question"): r for r in new_results}
    
    for prev_result in previous_results:
        question = prev_result.get("question")
        if question not in new_results_map:
            continue
        
        prev_category = prev_result.get("error_category")
        new_result = new_results_map[question]
        new_category = new_result.get("error_category")
        
        # Check if improved
        if prev_category in ["timeout", "api_error", "authorization_required", "empty_response", "unknown"]:
            if new_category in ["no_sql_generated", None]:  # None = success with SQL
                # Improved!
                improvements[prev_category] = improvements.get(prev_category, 0) + 1
            else:
                # Still failing
                display_cat = "success" if new_category is None else new_category
                still_failing[display_cat] = still_failing.get(display_cat, 0) + 1
    
    logger.info(f"\n{'='*80}")
    logger.info("RETEST SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Total questions retested: {len(new_results)}")
    logger.info(f"Improved (now responding): {sum(improvements.values())}")
    logger.info(f"Still failing: {sum(still_failing.values())}")
    
    if improvements:
        logger.info(f"\n✓ Improvements by original error type:")
        for cat, count in sorted(improvements.items()):
            logger.info(f"  {cat} → success: {count}")
    
    if still_failing:
        logger.info(f"\n✗ Still failing:")
        for cat, count in sorted(still_failing.items()):
            logger.info(f"  {cat}: {count}")
    
    # Final merged statistics
    logger.info(f"\n{'='*80}")
    logger.info("MERGED RESULTS STATISTICS")
    logger.info(f"{'='*80}")
    
    merged_categories = {}
    for r in merged_results:
        cat = r.get("error_category")
        # Use "success" as key for None (successful SQL generation)
        display_cat = "success (SQL generated)" if cat is None else cat
        merged_categories[display_cat] = merged_categories.get(display_cat, 0) + 1
    
    logger.info(f"Total questions: {len(merged_results)}")
    logger.info(f"\nCategory breakdown:")
    for cat, count in sorted(merged_categories.items()):
        logger.info(f"  {cat}: {count}")
    
    logger.info(f"\nMerged results saved to:")
    logger.info(f"  Excel: {excel_file}")
    logger.info(f"  JSON: {json_file}")
    logger.info(f"{'='*80}")


def generate_retest_filename(original_json_path: str) -> tuple:
    """
    Generate filenames for retest results.
    
    Pattern: 
    - original_name_retest_1.{json,xlsx} for first retest
    - original_name_retest_2.{json,xlsx} for second retest
    - Strips previous _retest_N and increments
    
    Examples:
    - agent_test_results_20260120.json → agent_test_results_20260120_retest_1.json
    - agent_test_results_20260120_retest_1.json → agent_test_results_20260120_retest_2.json
    - agent_test_results_20260120_retest_2.json → agent_test_results_20260120_retest_3.json
    
    Args:
        original_json_path: Path to original or previous retest JSON results file
        
    Returns:
        Tuple of (json_path, excel_path)
    """
    from pathlib import Path
    import re
    
    original_path = Path(original_json_path)
    base_name = original_path.stem  # Remove .json extension
    directory = original_path.parent
    
    # Extract base name and current retest number
    match = re.match(r'^(.+?)(?:_retest_(\d+))?$', base_name)
    if match:
        core_name = match.group(1)
        current_retest_num = int(match.group(2)) if match.group(2) else 0
        next_retest_num = current_retest_num + 1
    else:
        core_name = base_name
        next_retest_num = 1
    
    retest_json = directory / f"{core_name}_retest_{next_retest_num}.json"
    retest_excel = directory / f"{core_name}_retest_{next_retest_num}.xlsx"
    
    return str(retest_json), str(retest_excel)


def main():
    """
    Main entry point.
    
    Environment Setup:
        - Loads .env file if present
        - Validates required environment variables
        - Sets defaults for optional variables
    
    Command Line:
        python scripts/test_agent_from_excel.py [excel_file_path] [--max-workers N] [--retest-from JSON] [--recurse N]
        
        If no path provided, uses default:
        "Gemini Evaluation Questions _ With Screenshots.xlsx"
        
        Options:
            --max-workers N       Number of parallel workers (default: 10)
            --retest-from JSON    Retest failures from previous results file
            --recurse N           Number of automatic retest iterations (default: 1)
    
    Exit Codes:
        0 - Success
        1 - Error (missing env vars, file not found, or test failure)
    """
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Test a Data Insights Agent with questions from Excel file (with parallel execution)"
    )
    parser.add_argument(
        'excel_path',
        nargs='?',
        default="Gemini Evaluation Questions _ With Screenshots.xlsx",
        help="Path to Excel file with questions (default: Gemini Evaluation Questions _ With Screenshots.xlsx)"
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=10,
        help="Maximum number of parallel workers (default: 10)"
    )
    parser.add_argument(
        '--retest-from',
        type=str,
        default=None,
        help="Path to previous results JSON file to retest failures (e.g., agent_test_results_20260120_224454.json)"
    )
    parser.add_argument(
        '--recurse',
        type=int,
        default=1,
        help="Number of retest iterations to run automatically (default: 1, use with --retest-from)"
    )
    args = parser.parse_args()
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
    
    # Get args
    excel_path = args.excel_path
    max_workers = args.max_workers
    retest_from = args.retest_from
    recurse_count = args.recurse
    
    # RETEST MODE: Load previous results and retest failures
    if retest_from:
        logger.info(f"\n{'='*80}")
        logger.info("RETEST MODE ENABLED")
        logger.info(f"{'='*80}\n")
        
        if not os.path.exists(retest_from):
            logger.error(f"Previous results file not found: {retest_from}")
            sys.exit(1)
        
        # Validate recurse count
        if recurse_count < 1:
            logger.error(f"Invalid --recurse value: {recurse_count}. Must be >= 1")
            sys.exit(1)
        
        logger.info(f"Recursive retests: {recurse_count} iteration(s)")
        
        # Initialize agent client once
        logger.info(f"\nInitializing agent client for agent: {agent_id}")
        max_connections = max(100, max_workers + 20)
        client = AgentClient(
            project_id=project_id,
            location=location,
            engine_id=engine_id,
            agent_id=agent_id,
            max_connections=max_connections
        )
        
        logger.info(f"Configuration:")
        logger.info(f"  Project: {project_id}")
        logger.info(f"  Location: {location}")
        logger.info(f"  Engine: {engine_id}")
        logger.info(f"  Agent: {agent_id}")
        logger.info(f"  Session mode: {'Single session (conversational)' if use_same_session else 'New session per question'}")
        logger.info(f"  Max workers: {max_workers}")
        
        # Run recursive retests
        current_json_file = retest_from
        for iteration in range(1, recurse_count + 1):
            logger.info(f"\n{'='*80}")
            logger.info(f"RETEST ITERATION {iteration}/{recurse_count}")
            logger.info(f"{'='*80}\n")
            
            # Load previous results
            logger.info(f"Loading results from: {current_json_file}")
            previous_results = load_previous_results(current_json_file)
            logger.info(f"  Total questions: {len(previous_results)}")
            
            # Identify questions to retest
            retest_questions = identify_retest_questions(previous_results)
            logger.info(f"  Questions requiring retest: {len(retest_questions)}")
            
            if not retest_questions:
                logger.info("\n✓ No questions require retesting! All questions either:")
                logger.info("  - Succeeded (SQL extracted)")
                logger.info("  - Responded without SQL (no_sql_generated)")
                if iteration == 1:
                    logger.info(f"\nNo failures to retest!")
                else:
                    logger.info(f"\nAll failures resolved after {iteration - 1} retest iteration(s)!")
                break
            
            # Show categories being retested
            retest_categories = {}
            for result in previous_results:
                if result.get("question") in retest_questions:
                    cat = result.get("error_category", "unknown")
                    retest_categories[cat] = retest_categories.get(cat, 0) + 1
            
            logger.info(f"\nRetesting error categories:")
            for cat, count in sorted(retest_categories.items()):
                logger.info(f"  {cat}: {count}")
            
            # Generate retest output filenames
            retest_json, retest_excel = generate_retest_filename(current_json_file)
            logger.info(f"\nIteration {iteration} results will be saved to:")
            logger.info(f"  JSON: {retest_json}")
            logger.info(f"  Excel: {retest_excel}\n")
            
            # Test only the retest questions
            logger.info(f"{'='*80}")
            logger.info(f"RUNNING {len(retest_questions)} QUESTIONS IN PARALLEL")
            logger.info(f"{'='*80}\n")
            
            # Process retest questions in parallel
            TIMEOUT_SECONDS = 180
            new_results = _process_questions_parallel(
                client, retest_questions, max_workers, retest_json, retest_excel, TIMEOUT_SECONDS
            )
            
            # Merge with previous results
            logger.info(f"\nMerging retest results with original results...")
            merged_results = merge_results(previous_results, new_results)
            
            # Save merged results
            try:
                with open(retest_json, 'w') as f:
                    json.dump(merged_results, f, indent=2)
                save_results_to_excel(merged_results, retest_excel)
                logger.info(f"✓ Merged results saved")
            except Exception as e:
                logger.error(f"Error saving merged results: {e}")
            
            # Print retest summary
            print_retest_summary(previous_results, new_results, merged_results, retest_excel, retest_json)
            
            # Update current file for next iteration
            current_json_file = retest_json
        
        logger.info(f"\n{'='*80}")
        logger.info(f"RETEST COMPLETE - {recurse_count} iteration(s) executed")
        logger.info(f"{'='*80}")
        logger.info(f"Final results: {current_json_file}")
        
        sys.exit(0)
    
    # NORMAL MODE: Fresh test run
    if not os.path.exists(excel_path):
        logger.error(f"Excel file not found: {excel_path}")
        logger.error("Usage: python scripts/test_agent_from_excel.py [path/to/questions.xlsx] [--max-workers N]")
        sys.exit(1)
    
    logger.info(f"Configuration:")
    logger.info(f"  Project: {project_id}")
    logger.info(f"  Location: {location}")
    logger.info(f"  Engine: {engine_id}")
    logger.info(f"  Agent: {agent_id}")
    logger.info(f"  Session mode: {'Single session (conversational)' if use_same_session else 'New session per question'}")
    logger.info(f"  Max workers: {max_workers}")
    logger.info(f"  Excel file: {excel_path}")
    
    # Run the test
    try:
        results = test_agent_with_questions(
            excel_path=excel_path,
            project_id=project_id,
            location=location,
            engine_id=engine_id,
            agent_id=agent_id,
            use_same_session=use_same_session,
            max_workers=max_workers
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
