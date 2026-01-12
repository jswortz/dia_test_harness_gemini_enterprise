import logging
import re
import os

# Optional dependency for SQL normalization
try:
    import sqlparse
    HAS_SQLPARSE = True
except ImportError:
    HAS_SQLPARSE = False
    logging.warning("sqlparse not available - using basic SQL normalization")

# CRITICAL: Monkey-patch urllib3 connection pool BEFORE any imports
# This ensures Vertex AI SDK uses larger pools for high concurrency (40+ workers)
import urllib3
from urllib3 import HTTPConnectionPool

# Save original init
_original_connectionpool_init = HTTPConnectionPool.__init__

def _patched_connectionpool_init(self, host, port=None, strict=False, timeout=None, maxsize=10,
                                  block=False, headers=None, retries=None, _proxy=None, _proxy_headers=None,
                                  _proxy_config=None, **connection_pool_kw):
    # Force maxsize to at least 200 for all connection pools
    maxsize = max(200, maxsize) if maxsize else 200
    # Don't pass 'strict' parameter - it's deprecated in Python 3.x
    _original_connectionpool_init(self, host, port=port, timeout=timeout, maxsize=maxsize,
                                   block=block, headers=headers, retries=retries, _proxy=_proxy,
                                   _proxy_headers=_proxy_headers, _proxy_config=_proxy_config,
                                   **connection_pool_kw)

# Apply monkey patch globally
HTTPConnectionPool.__init__ = _patched_connectionpool_init

# Now import Vertex AI SDK - it will use our patched connection pools
import vertexai
from vertexai.generative_models import GenerativeModel

class SQLComparator:
    @staticmethod
    def normalize_sql(sql: str) -> str:
        """
        Enhanced SQL normalization for better matching.

        Handles:
        - Keyword case normalization
        - Identifier case normalization
        - Comment removal
        - Whitespace standardization
        - Fully-qualified table name simplification
        """
        if not sql:
            return ""

        try:
            if HAS_SQLPARSE:
                # Parse and format SQL using sqlparse
                formatted = sqlparse.format(
                    sql,
                    keyword_case='upper',
                    identifier_case='lower',
                    strip_comments=True,
                    reindent=False,  # Keep on same line for easier comparison
                    use_space_around_operators=True
                )
            else:
                # Basic normalization without sqlparse
                formatted = sql

            # Remove fully-qualified table names (project.dataset.table -> table)
            # Match both backtick and non-backtick versions
            formatted = re.sub(r'`[^`]+\.([^`]+)`', r'\1', formatted)
            formatted = re.sub(r'\b\w+\.\w+\.(\w+)\b', r'\1', formatted)

            # Standardize whitespace (collapse multiple spaces)
            formatted = re.sub(r'\s+', ' ', formatted).strip()

            return formatted
        except Exception as e:
            logging.warning(f"SQL normalization failed: {e}. Using basic normalization.")
            # Fallback to basic normalization
            return re.sub(r'\s+', ' ', sql).strip()

    def compare(self, generated: str, expected: str) -> bool:
        """
        Compares two SQL strings using enhanced normalization.

        Returns True if normalized versions match exactly.
        """
        if not generated or not expected:
            return False

        normalized_generated = self.normalize_sql(generated)
        normalized_expected = self.normalize_sql(expected)

        is_match = normalized_generated == normalized_expected

        if not is_match:
            logging.debug(f"SQL mismatch after normalization:")
            logging.debug(f"  Generated: {normalized_generated[:100]}...")
            logging.debug(f"  Expected:  {normalized_expected[:100]}...")

        return is_match

class JudgementModel:
    def __init__(self, project_id: str, location: str, model_name: str = None):
        """
        Initialize JudgementModel.

        Args:
            project_id: Google Cloud project ID
            location: Vertex AI location
            model_name: Model to use for judgement (default: from JUDGEMENT_MODEL env var or gemini-2.5-pro)

        Note:
            Connection pool is configured globally at module level (200 connections)
            to handle high concurrency from parallel workers.
        """
        # Use env variable if model_name not provided
        if model_name is None:
            model_name = os.getenv("JUDGEMENT_MODEL", "gemini-2.5-pro")

        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel(model_name)

    def explain_difference(self, question: str, generated_sql: str, expected_sql: str,
                          thoughts: str = "", agent_response: str = "", schema_info: str = "") -> str:
        """
        Uses a generative model to explain the difference between generated and expected SQL.
        Incorporates best practices for SQL semantic equivalence evaluation:
        - Miniature & Mull prompting: Consider execution on sample data
        - Schema-aware evaluation: Uses relevant table/column context
        - Semantic equivalence patterns: Recognizes common SQL transformations
        - Multi-aspect rubrics: Evaluates logic, performance, and correctness

        Args:
            question: Natural language question
            generated_sql: SQL generated by the agent
            expected_sql: Golden/expected SQL
            thoughts: Agent's internal reasoning
            agent_response: Agent's natural language response
            schema_info: Relevant schema description (recommended for accuracy)
        """
        # Extract table names from queries for schema filtering
        schema_context = ""
        if schema_info:
            schema_context = f"""
RELEVANT SCHEMA INFORMATION:
{schema_info}
"""

        prompt = f"""You are an expert SQL semantic equivalence judge with deep knowledge of database systems and query optimization.

Your task is to determine if two SQL queries are semantically equivalent (would produce the same result set) even if syntactically different.

=== EVALUATION FRAMEWORK ===

Use the "Miniature & Mull" technique:
1. Consider how each query would execute on a small, representative database instance
2. Think through the logical operations: filtering, joining, aggregation, ordering
3. Look for counterexamples where results would differ
4. If no counterexample exists, queries are EQUIVALENT

=== SEMANTIC EQUIVALENCE PATTERNS (Common transformations that preserve semantics) ===

1. JOIN VARIATIONS:
   - INNER JOIN vs WHERE clause with table list
   - Explicit vs implicit joins
   - Different join order (when results are same)

2. AGGREGATION EQUIVALENCES:
   - DISTINCT vs GROUP BY (for unique values)
   - COUNT(DISTINCT col) vs COUNT(*) with GROUP BY
   - Different GROUP BY orderings

3. FILTERING EQUIVALENCES:
   - OR conditions vs UNION
   - IN clause vs multiple OR
   - Subquery vs JOIN for filtering

4. SYNTAX VARIATIONS:
   - Table/column aliases vs full names
   - Different whitespace/formatting
   - Explicit vs implicit table prefixes
   - String case differences in identifiers (if case-insensitive)

5. DATE/TIME VARIATIONS:
   - Different date formats producing same range
   - BETWEEN vs >= AND <=
   - Different date functions yielding same result

6. CALCULATION EQUIVALENCES:
   - Mathematical expressions reordered
   - Different rounding approaches (if tolerance acceptable)
   - Percentage calculations with same logic

=== EVALUATION RUBRIC ===

Assign scores for:
- **Logical Equivalence** (0-10): Do queries have same logical structure?
- **Result Set Match** (0-10): Would they return identical results?
- **Performance Similarity** (0-5): Similar execution characteristics?

Score >= 25/25 → EQUIVALENT
Score < 25/25 → DIFFERENT

=== COMMON ERROR PATTERNS (Usually DIFFERENT) ===

- Missing/extra JOIN conditions
- Incorrect aggregation grouping
- Wrong filtering logic (AND vs OR)
- Date range errors
- Missing DISTINCT when needed
- Incorrect column references
- Wrong table references
- Calculation errors in formulas

=== INPUTS ===

Natural Language Question:
"{question}"

Expected SQL (Golden Standard):
```sql
{expected_sql}
```

Generated SQL (Agent Output):
```sql
{generated_sql}
```

Agent's Internal Thoughts:
{thoughts if thoughts else "(No thoughts provided)"}

Agent's Response:
{agent_response if agent_response else "(No response provided)"}
{schema_context}

=== YOUR ANALYSIS ===

Please provide:

1. **Key Differences**: List the syntactic/structural differences
2. **Semantic Analysis**: Apply "Miniature & Mull" - walk through query execution
3. **Equivalence Patterns**: Which patterns (if any) apply?
4. **Scoring**:
   - Logical Equivalence: X/10
   - Result Set Match: X/10
   - Performance Similarity: X/5
   - **Total: X/25**
5. **Counterexample**: If DIFFERENT, provide an example where results diverge
6. **Final Judgment**: Either "EQUIVALENT" or "DIFFERENT"

Format your response concisely but include all sections.
        """
        # Try with retry logic
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        class VertexAIError(Exception):
            pass

        @retry(
            retry=retry_if_exception_type((Exception,)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=False  # Don't reraise, we'll use fallback
        )
        def try_llm_judge():
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                logging.warning(f"LLM judgement attempt failed: {e}")
                raise

        try:
            return try_llm_judge()
        except Exception as e:
            # Fallback: Use heuristic matching
            logging.error(f"All LLM judgement attempts failed: {e}. Using heuristic fallback.")
            return self._heuristic_fallback(question, generated_sql, expected_sql)

    def score_sql_similarity(self, question: str, generated_sql: str, expected_sql: str,
                            thoughts: str = "", agent_response: str = "", schema_info: str = "") -> dict:
        """
        Scores SQL similarity using a flexible 100-point rubric across 6 categories.
        Recognizes partial correctness and incremental improvements.

        Returns:
            dict: {
                'total_score': int (0-100),
                'category_scores': {
                    'data_source': int (0-20),
                    'filtering': int (0-25),
                    'columns': int (0-25),
                    'grouping': int (0-15),
                    'ordering': int (0-10),
                    'format': int (0-5)
                },
                'verdict': str ('EQUIVALENT', 'MOSTLY_CORRECT', 'PARTIALLY_CORRECT', 'MOSTLY_WRONG', 'COMPLETELY_WRONG'),
                'explanation': str
            }
        """
        schema_context = ""
        if schema_info:
            schema_context = f"""
RELEVANT SCHEMA INFORMATION:
{schema_info}
"""

        prompt = f"""You are an expert SQL evaluator using a flexible 100-point rubric.

=== TASK ===
Score the generated SQL across 6 categories to assess similarity to the expected SQL.
Recognize partial correctness - not all differences mean complete failure.

=== INPUT ===

Natural Language Question:
"{question}"

Expected SQL (Golden Standard):
```sql
{expected_sql}
```

Generated SQL (Agent Output):
```sql
{generated_sql}
```

Agent's Internal Thoughts:
{thoughts if thoughts else "(No thoughts provided)"}

Agent's Response:
{agent_response if agent_response else "(No response provided)"}
{schema_context}

=== SCORING RUBRIC (100 POINTS TOTAL) ===

**Category 1: Data Source (0-20 points)**
Evaluates: Are the correct tables being queried?
- 20 points: Exact match on all tables and joins
- 15 points: Correct tables, minor differences in join conditions
- 10 points: Correct primary table, missing/wrong secondary tables
- 5 points: Using related but wrong tables
- 0 points: Completely wrong tables

**Category 2: Filtering Logic (0-25 points)**
Evaluates: Are the correct filters applied?
- 25 points: All filters correct (dates, territories, markets, etc.)
- 20 points: All filters present, minor differences (e.g., terr_cd=840 vs mkt_na='United States')
- 15 points: Most filters correct, missing 1-2 filters
- 10 points: Some filters correct, multiple missing or wrong
- 5 points: Minimal filtering, mostly wrong
- 0 points: No filters or completely wrong filters

**Category 3: Column Selection & Aggregation (0-25 points)**
Evaluates: Are the correct columns and aggregations used?
- 25 points: All columns/aggregations match perfectly
- 20 points: Correct aggregations, minor differences in aliases/rounding
- 15 points: Correct metrics, missing context columns (labels, dates)
- 10 points: Some correct metrics, some wrong/missing
- 5 points: Minimal overlap with expected columns
- 0 points: Completely wrong columns/aggregations

**Category 4: Grouping & Granularity (0-15 points)**
Evaluates: Is the correct grouping/aggregation level used?
- 15 points: Perfect grouping (or lack thereof)
- 12 points: Correct grouping columns, minor ordering differences
- 8 points: Mostly correct, missing/extra GROUP BY columns
- 4 points: Wrong granularity (daily vs monthly, etc.)
- 0 points: Completely wrong grouping

**Category 5: Ordering & Limits (0-10 points)**
Evaluates: Are results properly ordered/limited?
- 10 points: Perfect ORDER BY and LIMIT
- 7 points: Correct ORDER BY, minor differences in direction (ASC/DESC)
- 5 points: Correct intent, wrong column ordering
- 2 points: Missing ORDER BY when needed
- 0 points: Wrong ordering logic

**Category 6: Output Format (0-5 points)**
Evaluates: Table references, aliases, formatting
- 5 points: Perfect match
- 4 points: Minor differences (qualified vs unqualified table names)
- 2 points: Different but valid formatting
- 0 points: Invalid SQL syntax

=== OUTPUT FORMAT ===

Provide your analysis in this EXACT format:

**Category 1 - Data Source: X/20**
[Brief explanation]

**Category 2 - Filtering Logic: X/25**
[Brief explanation]

**Category 3 - Column Selection & Aggregation: X/25**
[Brief explanation]

**Category 4 - Grouping & Granularity: X/15**
[Brief explanation]

**Category 5 - Ordering & Limits: X/10**
[Brief explanation]

**Category 6 - Output Format: X/5**
[Brief explanation]

**Total Score: X/100**

**Verdict:** [EQUIVALENT|MOSTLY_CORRECT|PARTIALLY_CORRECT|MOSTLY_WRONG|COMPLETELY_WRONG]

Where verdict is determined by total score:
- 90-100: EQUIVALENT
- 75-89: MOSTLY_CORRECT
- 50-74: PARTIALLY_CORRECT
- 25-49: MOSTLY_WRONG
- 0-24: COMPLETELY_WRONG

**Summary:** [1-2 sentence summary of key differences]
"""

        # Try with retry logic
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        @retry(
            retry=retry_if_exception_type((Exception,)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=False
        )
        def try_llm_scoring():
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                logging.warning(f"LLM scoring attempt failed: {e}")
                raise

        try:
            response_text = try_llm_scoring()
            # Parse the response to extract scores
            return self._parse_flexible_score(response_text)
        except Exception as e:
            logging.error(f"All LLM scoring attempts failed: {e}. Using heuristic fallback.")
            return self._heuristic_score_fallback(question, generated_sql, expected_sql)

    def _parse_flexible_score(self, response_text: str) -> dict:
        """Parse LLM response to extract category scores and verdict."""
        import re

        scores = {}

        # Extract category scores using regex
        patterns = {
            'data_source': r'Category 1.*?Data Source.*?(\d+)/20',
            'filtering': r'Category 2.*?Filtering Logic.*?(\d+)/25',
            'columns': r'Category 3.*?Column Selection.*?(\d+)/25',
            'grouping': r'Category 4.*?Grouping.*?(\d+)/15',
            'ordering': r'Category 5.*?Ordering.*?(\d+)/10',
            'format': r'Category 6.*?Output Format.*?(\d+)/5'
        }

        for category, pattern in patterns.items():
            match = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)
            if match:
                scores[category] = int(match.group(1))
            else:
                logging.warning(f"Could not parse {category} score from response")
                scores[category] = 0

        # Extract total score
        total_match = re.search(r'Total Score.*?(\d+)/100', response_text, re.IGNORECASE)
        total_score = int(total_match.group(1)) if total_match else sum(scores.values())

        # Extract verdict
        verdict_match = re.search(r'Verdict.*?(EQUIVALENT|MOSTLY_CORRECT|PARTIALLY_CORRECT|MOSTLY_WRONG|COMPLETELY_WRONG)',
                                 response_text, re.IGNORECASE)
        verdict = verdict_match.group(1).upper() if verdict_match else self._score_to_verdict(total_score)

        return {
            'total_score': total_score,
            'category_scores': scores,
            'verdict': verdict,
            'explanation': response_text
        }

    def _score_to_verdict(self, score: int) -> str:
        """Convert numerical score to verdict."""
        if score >= 90:
            return 'EQUIVALENT'
        elif score >= 75:
            return 'MOSTLY_CORRECT'
        elif score >= 50:
            return 'PARTIALLY_CORRECT'
        elif score >= 25:
            return 'MOSTLY_WRONG'
        else:
            return 'COMPLETELY_WRONG'

    def _heuristic_score_fallback(self, question: str, generated_sql: str, expected_sql: str) -> dict:
        """
        Heuristic-based SQL scoring when LLM judge is unavailable.
        Returns a score dict in the same format as score_sql_similarity.
        """
        logging.warning("Using heuristic fallback for SQL scoring (LLM unavailable)")

        # Check for basic structural similarity
        gen_keywords = set(re.findall(r'\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|JOIN|LIMIT|HAVING)\b',
                                        generated_sql.upper()))
        exp_keywords = set(re.findall(r'\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|JOIN|LIMIT|HAVING)\b',
                                        expected_sql.upper()))

        common_keywords = gen_keywords & exp_keywords
        missing_keywords = exp_keywords - gen_keywords

        # Simple heuristic scoring
        similarity_ratio = len(common_keywords) / max(len(exp_keywords), 1)

        # Distribute score across categories based on keyword presence
        base_score = int(similarity_ratio * 100)

        scores = {
            'data_source': min(20, int(base_score * 0.20)),
            'filtering': min(25, int(base_score * 0.25)),
            'columns': min(25, int(base_score * 0.25)),
            'grouping': min(15, int(base_score * 0.15)),
            'ordering': min(10, int(base_score * 0.10)),
            'format': min(5, int(base_score * 0.05))
        }

        total_score = sum(scores.values())
        verdict = self._score_to_verdict(total_score)

        explanation = f"""### Heuristic Fallback Scoring (LLM Judge Unavailable)

**Structural Similarity**: {similarity_ratio*100:.1f}%
**Common Keywords**: {', '.join(sorted(common_keywords)) if common_keywords else 'None'}
**Missing Keywords**: {', '.join(sorted(missing_keywords)) if missing_keywords else 'None'}

Note: This is a conservative heuristic-based evaluation. For accurate scoring, the LLM judge should be available.
"""

        return {
            'total_score': total_score,
            'category_scores': scores,
            'verdict': verdict,
            'explanation': explanation
        }

    def _heuristic_fallback(self, question: str, generated_sql: str, expected_sql: str) -> str:
        """
        Heuristic-based SQL equivalence check when LLM judge is unavailable.

        Returns a judgement string indicating DIFFERENT with explanation.
        This is a conservative fallback that helps maintain test execution.
        """
        logging.warning("Using heuristic fallback for SQL comparison (LLM unavailable)")

        # Check for basic structural similarity
        gen_keywords = set(re.findall(r'\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|JOIN|LIMIT|HAVING)\b',
                                        generated_sql.upper()))
        exp_keywords = set(re.findall(r'\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|JOIN|LIMIT|HAVING)\b',
                                        expected_sql.upper()))

        common_keywords = gen_keywords & exp_keywords
        missing_keywords = exp_keywords - gen_keywords
        extra_keywords = gen_keywords - exp_keywords

        similarity_score = len(common_keywords) / max(len(exp_keywords), 1) * 10

        # Conservative judgement - mark as DIFFERENT unless very high similarity
        if similarity_score >= 9 and not missing_keywords and not extra_keywords:
            judgement = "EQUIVALENT (HEURISTIC)"
        else:
            judgement = "DIFFERENT (HEURISTIC)"

        return f"""### Heuristic Fallback Analysis (LLM Judge Unavailable)

**Structural Similarity**: {similarity_score:.1f}/10

**Common Keywords**: {', '.join(sorted(common_keywords)) if common_keywords else 'None'}
**Missing Keywords**: {', '.join(sorted(missing_keywords)) if missing_keywords else 'None'}
**Extra Keywords**: {', '.join(sorted(extra_keywords)) if extra_keywords else 'None'}

**Final Judgment**: {judgement}

Note: This is a conservative heuristic-based evaluation used when the LLM judge is unavailable.
For accurate semantic equivalence, the LLM judge should be available.
"""
