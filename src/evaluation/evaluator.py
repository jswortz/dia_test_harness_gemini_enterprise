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
