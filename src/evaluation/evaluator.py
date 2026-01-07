import logging
import re
import vertexai
from vertexai.generative_models import GenerativeModel

class SQLComparator:
    def compare(self, generated: str, expected: str) -> bool:
        """
        Compares two SQL strings for exact match, ignoring leading/trailing whitespace
        and collapsing internal whitespace to single spaces.
        """
        if not generated or not expected:
            return False
            
        def normalize(s):
            # Replace multiple whitespace with single space and strip
            return re.sub(r'\s+', ' ', s).strip()
            
        return normalize(generated) == normalize(expected)

class JudgementModel:
    def __init__(self, project_id: str, location: str, model_name: str = "gemini-3-pro-preview"):
        # User requested global location for judgement model
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel(model_name)

    def explain_difference(self, question: str, generated_sql: str, expected_sql: str, thoughts: str = "", agent_response: str = "") -> str:
        """
        Uses a generative model to explain the difference between generated and expected SQL.
        Considers agent thoughts and natural language response for context.
        """
        prompt = f"""
You are an expert SQL analyst. 
I have a Natural Language Question, a Generated SQL query (if any), and an Expected (Golden) SQL query.
I also have the Agent's internal thoughts and final natural language response.
The Generated SQL did not match the Expected SQL exactly.
Please explain the difference and determine if the Generated SQL is semantically equivalent or incorrect.
Consider the Agent's thoughts to understand its intent or failure mode.

Question: "{question}"

Expected SQL:
```sql
{expected_sql}
```

Generated SQL:
```sql
{generated_sql}
```

Agent Thoughts:
{thoughts}

Agent Response:
{agent_response}

Please provide a concise explanation of the differences and a final judgement: "EQUIVALENT" or "DIFFERENT".
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logging.error(f"Error generating judgement: {e}")
            return f"Error resolving judgment: {str(e)}"
