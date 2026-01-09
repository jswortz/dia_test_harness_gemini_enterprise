import json
import uuid
import re
from pathlib import Path
from typing import List, Dict
import pandas as pd


class GoldenSetLoader:
    def load(self, path: str) -> List[Dict]:
        """
        Loads golden set from JSON, CSV, or Excel file.
        Auto-detects format based on file extension.
        """
        file_path = Path(path)
        extension = file_path.suffix.lower()

        if extension == '.json':
            return self._load_json(path)
        elif extension in ['.csv', '.xlsx', '.xls']:
            return self._load_tabular(path)
        else:
            raise ValueError(f"Unsupported file format: {extension}. Use .json, .csv, .xlsx, or .xls")

    def _load_json(self, path: str) -> List[Dict]:
        """Loads the golden set JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        return data

    def _load_tabular(self, path: str) -> List[Dict]:
        """
        Loads golden set from CSV or Excel file.
        Expected columns: nl_question, expected_sql (or variations like 'Question', 'Expected SQL')
        Auto-generates: question_id (UUID), complexity, sql_pattern, expected_result_type
        """
        file_path = Path(path)
        extension = file_path.suffix.lower()

        # Load dataframe based on format
        if extension == '.csv':
            df = pd.read_csv(path)
        elif extension in ['.xlsx', '.xls']:
            df = pd.read_excel(path)
        else:
            raise ValueError(f"Unsupported tabular format: {extension}")

        # Normalize column names to handle different variations
        df.columns = df.columns.str.strip()
        column_mapping = {}

        # Map question column (case-insensitive, handles underscores/spaces)
        question_variants = ['nl_question', 'question', 'nl question', 'nlquestion']
        for col in df.columns:
            col_normalized = col.lower().replace('_', ' ').replace('-', ' ').strip()
            if col_normalized in question_variants:
                column_mapping[col] = 'nl_question'
                break

        # Map SQL column
        sql_variants = ['expected_sql', 'expected sql', 'sql', 'expectedsql', 'query']
        for col in df.columns:
            col_normalized = col.lower().replace('_', ' ').replace('-', ' ').strip()
            if col_normalized in sql_variants:
                column_mapping[col] = 'expected_sql'
                break

        # Apply column renaming
        if column_mapping:
            df = df.rename(columns=column_mapping)

        # Validate required columns
        required_columns = ['nl_question', 'expected_sql']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            available_cols = list(df.columns)
            raise ValueError(
                f"Missing required columns: {missing_columns}. "
                f"Available columns: {available_cols}. "
                f"Expected columns like: 'nl_question'/'question' and 'expected_sql'/'sql'"
            )

        # Convert to list of dictionaries with auto-generated fields
        golden_set = []
        for _, row in df.iterrows():
            question = str(row['nl_question']).strip()
            expected_sql = str(row['expected_sql']).strip()

            # Auto-generate fields
            test_case = {
                'question_id': str(uuid.uuid4()),
                'nl_question': question,
                'complexity': self._infer_complexity(expected_sql),
                'expected_sql': expected_sql,
                'sql_pattern': self._generate_sql_pattern(expected_sql),
                'expected_result_type': self._infer_result_type(expected_sql)
            }
            golden_set.append(test_case)

        return golden_set

    def _infer_complexity(self, sql: str) -> str:
        """
        Infers SQL complexity based on query structure.

        Simple: Basic SELECT with simple aggregation or filter
        Medium: GROUP BY, multiple JOINs, or subqueries
        Complex: Multiple subqueries, CTEs, window functions, or complex joins
        """
        sql_upper = sql.upper()

        # Count complexity indicators
        has_group_by = 'GROUP BY' in sql_upper
        has_join = 'JOIN' in sql_upper
        has_subquery = sql_upper.count('SELECT') > 1
        has_cte = 'WITH' in sql_upper
        has_window = any(func in sql_upper for func in ['ROW_NUMBER(', 'RANK(', 'DENSE_RANK(', 'OVER('])

        # Count number of joins
        join_count = sql_upper.count('JOIN')

        # Determine complexity
        complexity_score = 0
        if has_cte or has_window:
            complexity_score += 3
        if has_subquery:
            complexity_score += 2
        if has_group_by:
            complexity_score += 1
        if join_count >= 2:
            complexity_score += 2
        elif has_join:
            complexity_score += 1

        if complexity_score >= 4:
            return "Complex"
        elif complexity_score >= 2:
            return "Medium"
        else:
            return "Simple"

    def _generate_sql_pattern(self, sql: str) -> str:
        """
        Generates a regex pattern for the SQL query.
        Replaces table names with wildcards while preserving query structure.
        """
        # Normalize whitespace
        pattern = re.sub(r'\s+', r'\\s+', sql.strip())

        # Replace fully qualified table names (project.dataset.table or `project.dataset.table`)
        pattern = re.sub(r'`[^`]+\.[^`]+\.[^`]+`', r'`.*`', pattern)

        # Replace simple table names
        pattern = re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\b', r'.*', pattern)

        # Escape special regex characters
        for char in ['(', ')', '[', ']', '{', '}', '.', '*', '+', '?', '^', '$', '|']:
            if char not in ['*', '+', '?']:  # Don't escape wildcards we added
                pattern = pattern.replace(char, '\\' + char)

        return pattern

    def _infer_result_type(self, sql: str) -> str:
        """
        Infers the expected result type from the SQL query.

        Looks at SELECT clause to determine if result is:
        - INTEGER (COUNT, SUM of integers)
        - FLOAT (AVG, SUM of floats)
        - STRING (column selection, CONCAT)
        - TABLE (multiple columns or GROUP BY)
        """
        sql_upper = sql.upper()

        # Extract SELECT clause (between SELECT and FROM)
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.IGNORECASE | re.DOTALL)
        if not select_match:
            return "UNKNOWN"

        select_clause = select_match.group(1).strip()

        # Check for aggregation functions
        if re.search(r'COUNT\s*\(', select_clause):
            return "INTEGER"
        elif re.search(r'AVG\s*\(', select_clause):
            return "FLOAT"
        elif re.search(r'SUM\s*\(', select_clause):
            return "NUMERIC"  # Could be INT or FLOAT
        elif select_clause == '*' or ',' in select_clause:
            return "TABLE"  # Multiple columns
        else:
            return "STRING"  # Single column selection
