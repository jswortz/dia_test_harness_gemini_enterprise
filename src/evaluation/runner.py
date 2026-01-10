import json
import logging
import time
from typing import List, Dict, Any
from datetime import datetime
from .data_loader import GoldenSetLoader
from .agent_client import AgentClient, AgentAuthorizationError
from .evaluator import SQLComparator, JudgementModel

class TestRunner:
    def __init__(
        self,
        loader: GoldenSetLoader,
        client: AgentClient,
        comparator: SQLComparator,
        judge: JudgementModel,
        output_path: str,
        schema_description: str = ""
    ):
        self.loader = loader
        self.client = client
        self.comparator = comparator
        self.judge = judge
        self.output_path = output_path
        self.schema_description = schema_description
        self.results = []

    def parse_response(self, raw_response: List[Dict]) -> Dict[str, str]:
        """
        Parses the raw agent response to extract thoughts, natural language response, and SQL.
        """
        thoughts = []
        response_parts = []
        
        # raw_response is expected to be a list of dicts (chunks)
        if not isinstance(raw_response, list):
             # Fallback if it's a single dict or string
             return {
                 "thoughts": "",
                 "response": str(raw_response),
                 "generated_sql": self._extract_sql_string(str(raw_response))
             }

        for chunk in raw_response:
            # Check for standard answer structure
            if 'answer' in chunk:
                for reply in chunk['answer'].get('replies', []):
                    content = reply.get('groundedContent', {}).get('content', {})
                    text = content.get('text', '')
                    is_thought = content.get('thought', False)
                    
                    if is_thought:
                        thoughts.append(text)
                    else:
                        response_parts.append(text)
            
            # Fallback for simple queryResult structure if used
            if 'queryResult' in chunk:
                # Typically responseMessages are final response, not thoughts
                msgs = chunk['queryResult'].get('responseMessages', [])
                for msg in msgs:
                     txt = msg.get('text', {}).get('text', [''])[0]
                     response_parts.append(txt)

        full_thoughts = "".join(thoughts).strip()
        full_response = "".join(response_parts).strip()
        
        # Extract SQL from response (prioritized) or thoughts
        generated_sql = self._extract_sql_string(full_response)
        if not generated_sql:
             generated_sql = self._extract_sql_string(full_thoughts)

        return {
            "thoughts": full_thoughts,
            "response": full_response,
            "generated_sql": generated_sql
        }

    def _extract_sql_string(self, text: str) -> str:
        """Helper to find SQL block in text."""
        import re
        # Look for markdown sql block
        match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
             return match.group(1).strip()
        
        # Look for generic code block if it starts with SELECT
        match = re.search(r"```\s*(SELECT.*?)```", text, re.DOTALL | re.IGNORECASE)
        if match:
             return match.group(1).strip()

        # Look for bare SELECT statement
        # Only if strict match at start of line
        match = re.search(r"(?m)^(SELECT\s+.*)", text, re.DOTALL | re.IGNORECASE)
        if match:
             return match.group(1).strip()
             
        return ""

    def run(self, input_path: str):
        """Runs the test against the golden set."""
        data = self.loader.load(input_path)
        
        print(f"Starting test run with {len(data)} items...")
        
    def _extract_session_id(self, raw_response: List[Dict]) -> str:
        """Extracts session ID from the last chunk of the response."""
        if not raw_response or not isinstance(raw_response, list):
            return None
        
        for chunk in reversed(raw_response):
            if "sessionInfo" in chunk and "session" in chunk["sessionInfo"]:
                return chunk["sessionInfo"]["session"]
        return None

    def run_single_test(self, test_case: Dict, session_id: str = None) -> Dict:
        """
        Run a single test case with specified session (for parallel execution).

        Args:
            test_case: Dict with 'nl_question', 'expected_sql', 'question_id'
            session_id: Optional session ID (creates new session if None)

        Returns:
            Dict with test result including SQL, match status, explanation, etc.
        """
        question = test_case["nl_question"]
        expected_sql = test_case["expected_sql"]
        question_id = test_case.get("question_id")

        start_time = time.time()
        try:
            # Create session if not provided
            if not session_id:
                session_id = self.client.create_session()

            # 1. Query Agent (First Query)
            raw_response_1 = self.client.query_agent(question, session_id=session_id)
            parsed_1 = self.parse_response(raw_response_1)

            # Capture thoughts and response from the actual answer
            thoughts = parsed_1["thoughts"]
            agent_response = parsed_1["response"]
            generated_sql = parsed_1["generated_sql"]

            # 2. Follow-up for SQL
            raw_response_2 = self.client.query_agent(
                "what was the sql query used for the previous answer?",
                session_id=session_id
            )
            parsed_2 = self.parse_response(raw_response_2)

            if parsed_2["generated_sql"]:
                generated_sql = parsed_2["generated_sql"]

            # 3. Compare
            is_match = self.comparator.compare(generated_sql, expected_sql)

            explanation = None
            if not is_match:
                explanation = self.judge.explain_difference(
                    question,
                    generated_sql,
                    expected_sql,
                    thoughts=thoughts,
                    agent_response=agent_response,
                    schema_info=self.schema_description
                )

            latency = time.time() - start_time

            result = {
                "question_id": question_id,
                "question": question,
                "expected_sql": expected_sql,
                "generated_sql": generated_sql,
                "thoughts": thoughts,
                "agent_response": agent_response,
                "is_match": is_match,
                "explanation": explanation,
                "latency": latency,
                "timestamp": datetime.utcnow().isoformat(),
                "raw_response": str(raw_response_1)[:1000]
            }
            return result

        except AgentAuthorizationError:
            # Re-raise authorization errors immediately
            raise
        except Exception as e:
            logging.error(f"Error processing {question}: {e}")
            return {
                "question_id": question_id,
                "question": question,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def run(self, input_path: str):
        """Runs the test against the golden set."""
        data = self.loader.load(input_path)

        print(f"Starting test run with {len(data)} items...")

        for item in data:
            question = item["nl_question"]
            expected_sql = item["expected_sql"]
            question_id = item.get("question_id")

            print(f"Processing: {question}")

            start_time = time.time()
            try:
                # 1. Query Agent (First Valid Query)
                print("  Sending initial query...")
                raw_response_1 = self.client.query_agent(question)
                parsed_1 = self.parse_response(raw_response_1)

                session_id = self._extract_session_id(raw_response_1)

                # Capture thoughts and response from the actual answer
                thoughts = parsed_1["thoughts"]
                agent_response = parsed_1["response"]
                generated_sql = parsed_1["generated_sql"] # Try to get SQL from first turn if possible

                # 2. Follow-up for SQL if session exists and SQL missing (or always, per instruction?)
                # User said: "Use the nl_question for the test, then followup with 'what was the sql used'."
                # Implies we should ALWAYS follow up to be sure, or at least if we didn't find it.
                # But let's assume we do it to get the explicit SQL if not present.
                if session_id:
                     print(f"  Follow-up for SQL (Session: {session_id.split('/')[-1]})...")
                     raw_response_2 = self.client.query_agent("what was the sql query used for the previous answer?", session_id=session_id)
                     parsed_2 = self.parse_response(raw_response_2)

                     if parsed_2["generated_sql"]:
                         generated_sql = parsed_2["generated_sql"]
                         print("  SQL found in follow-up.")
                     elif parsed_2["response"]:
                         # Sometimes the agent just says the SQL in text without markdown
                         # We might want to look harder or just append it?
                         # For now, let's treat the text as potential SQL if it looks like it?
                         # Or just rely on the existing extraction logic.
                         pass
                else:
                    print("  No session ID found, cannot follow up.")

                # 3. Compare
                is_match = self.comparator.compare(generated_sql, expected_sql)

                explanation = None
                if not is_match:
                    print("  Mismatch detected. Asking for judgement...")
                    explanation = self.judge.explain_difference(
                        question,
                        generated_sql,
                        expected_sql,
                        thoughts=thoughts,
                        agent_response=agent_response,
                        schema_info=self.schema_description
                    )

                latency = time.time() - start_time

                result = {
                    "question_id": question_id,
                    "question": question,
                    "expected_sql": expected_sql,
                    "generated_sql": generated_sql,
                    "thoughts": thoughts,
                    "agent_response": agent_response,
                    "is_match": is_match,
                    "explanation": explanation,
                    "latency": latency,
                    "timestamp": datetime.utcnow().isoformat(),
                    "raw_response": str(raw_response_1)[:1000] # Keep first response for debug context
                }
                self.results.append(result)

            except AgentAuthorizationError:
                # Re-raise authorization errors immediately - don't continue evaluation
                raise
            except Exception as e:
                logging.error(f"Error processing {question}: {e}")
                self.results.append({
                    "question_id": question_id,
                    "question": question,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })

        self.save_results()
        print(f"Run complete. Results saved to {self.output_path}")

    def save_results(self):
        with open(self.output_path, 'w') as f:
            for res in self.results:
                f.write(json.dumps(res) + "\n")

    def calculate_metrics(self, results: List[Dict] = None) -> Dict[str, Any]:
        """
        Calculates accuracy metrics from test results.

        Returns:
            dict with keys:
                - total: total test cases
                - exact_match: count where is_match=True
                - semantically_equivalent: count where "EQUIVALENT" in explanation
                - failures: count where "DIFFERENT" in explanation or no SQL generated
                - accuracy: (exact_match + semantically_equivalent) / total * 100
                - error_count: count of tests with errors
        """
        if results is None:
            results = self.results

        total = len(results)
        exact_match = 0
        semantically_equivalent = 0
        failures = 0
        error_count = 0

        for result in results:
            # Skip error cases
            if 'error' in result:
                error_count += 1
                failures += 1
                continue

            # Exact match
            if result.get('is_match', False):
                exact_match += 1
            # Semantic equivalence via LLM judge
            elif result.get('explanation'):
                explanation = result['explanation'].upper()
                if 'EQUIVALENT' in explanation:
                    semantically_equivalent += 1
                elif 'DIFFERENT' in explanation:
                    failures += 1
                else:
                    # Unclear judgment
                    failures += 1
            else:
                # No explanation and no match means likely no SQL generated or comparison failed
                failures += 1

        # Calculate accuracy percentage
        successful = exact_match + semantically_equivalent
        accuracy = (successful / total * 100) if total > 0 else 0.0

        return {
            'total': total,
            'exact_match': exact_match,
            'semantically_equivalent': semantically_equivalent,
            'failures': failures,
            'error_count': error_count,
            'accuracy': round(accuracy, 2)
        }

    def extract_failures(self, results: List[Dict] = None) -> List[Dict]:
        """
        Extracts failed test cases with detailed information.

        Returns:
            List of dicts with keys:
                - question_id
                - question
                - expected_sql
                - generated_sql
                - issue (description of failure type)
                - explanation (from LLM judge)
        """
        if results is None:
            results = self.results

        failures = []

        for result in results:
            # Skip successful exact matches
            if result.get('is_match', False):
                continue

            # Determine failure type
            issue = "Unknown failure"
            if 'error' in result:
                issue = f"Error: {result['error']}"
            elif not result.get('generated_sql'):
                issue = "No SQL generated"
            elif result.get('explanation'):
                explanation_upper = result['explanation'].upper()
                if 'DIFFERENT' in explanation_upper:
                    # Try to extract issue from explanation
                    # Common patterns: "column over-selection", "incorrect JOIN", etc.
                    issue = "Semantically different SQL"
                elif 'EQUIVALENT' in explanation_upper:
                    # This is actually a success (semantic match)
                    continue
                else:
                    issue = "Unclear judgment"
            else:
                issue = "SQL mismatch (no judgment)"

            failure_detail = {
                'question_id': result.get('question_id'),
                'question': result.get('question'),
                'expected_sql': result.get('expected_sql'),
                'generated_sql': result.get('generated_sql'),
                'issue': issue,
                'explanation': result.get('explanation', '')
            }
            failures.append(failure_detail)

        return failures
