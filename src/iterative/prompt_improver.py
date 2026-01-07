"""
PromptImprover: AI-driven prompt refinement based on failure analysis.

Uses Gemini LLM to:
- Analyze failure patterns
- Suggest specific prompt improvements
- Present improvements to user for approval/editing
"""

import vertexai
from vertexai.generative_models import GenerativeModel
from typing import List, Dict, Any, Optional, Tuple
import difflib


class PromptImprover:
    """
    Analyzes test failures and suggests prompt improvements using Gemini LLM.

    Provides:
    - Failure pattern analysis
    - Specific prompt improvement suggestions
    - User approval/editing interface
    - Diff visualization
    """

    def __init__(self, project_id: str, location: str = "global", model_name: str = "gemini-2.0-flash-exp"):
        """
        Initialize prompt improver.

        Args:
            project_id: Google Cloud project ID
            location: Location for Vertex AI (e.g., "global", "us-central1")
            model_name: Gemini model to use for analysis
        """
        self.project_id = project_id
        self.location = location
        self.model_name = model_name

        # Initialize Vertex AI
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel(model_name)

    def analyze_failures(self, failures: List[Dict], current_prompt: str) -> str:
        """
        Analyze failure patterns and suggest prompt improvements.

        Args:
            failures: List of failed test cases with details
            current_prompt: Current NL2SQL prompt text

        Returns:
            str: Suggested improved prompt
        """
        if not failures:
            print("No failures to analyze. Prompt is performing well!")
            return current_prompt

        print(f"\n=== Analyzing {len(failures)} Failures ===")

        # Build analysis prompt for LLM
        analysis_prompt = self._build_analysis_prompt(failures, current_prompt)

        # Generate suggestions
        print("Generating prompt improvement suggestions...")
        response = self.model.generate_content(analysis_prompt)
        suggested_prompt = response.text.strip()

        # Extract just the prompt if LLM included explanation
        # Look for common patterns like "Here is the improved prompt:" or code blocks
        if "```" in suggested_prompt:
            # Extract from code block
            lines = suggested_prompt.split("\n")
            in_code_block = False
            prompt_lines = []
            for line in lines:
                if line.strip().startswith("```"):
                    if in_code_block:
                        break  # End of code block
                    in_code_block = True
                    continue
                if in_code_block:
                    prompt_lines.append(line)
            if prompt_lines:
                suggested_prompt = "\n".join(prompt_lines).strip()

        return suggested_prompt

    def _build_analysis_prompt(self, failures: List[Dict], current_prompt: str) -> str:
        """
        Build the prompt for LLM to analyze failures and suggest improvements.

        Args:
            failures: List of failed test cases
            current_prompt: Current NL2SQL prompt

        Returns:
            str: Analysis prompt for LLM
        """
        # Summarize failures
        failure_summary = []
        for i, failure in enumerate(failures, 1):
            summary = f"\n{i}. Question: \"{failure['question']}\""
            summary += f"\n   Expected SQL: {failure['expected_sql']}"
            summary += f"\n   Generated SQL: {failure.get('generated_sql', 'None')}"
            summary += f"\n   Issue: {failure['issue']}"
            if failure.get('explanation'):
                # Include first 300 chars of explanation
                explanation = failure['explanation'][:300]
                summary += f"\n   LLM Judge: {explanation}"
            failure_summary.append(summary)

        failures_text = "\n".join(failure_summary)

        prompt = f"""You are an expert in prompt engineering for NL2SQL (Natural Language to SQL) systems.

I'm optimizing a Data Insights Agent that converts natural language questions into BigQuery SQL queries.

**Current NL2SQL Prompt:**
```
{current_prompt}
```

**Failed Test Cases:**
{failures_text}

**Your Task:**
Analyze the failure patterns and generate an IMPROVED version of the NL2SQL prompt that addresses these specific issues.

**Guidelines:**
1. Keep the overall structure and tone of the original prompt
2. Add specific, actionable instructions to fix the identified issues
3. Be concise - add only what's needed to address the failures
4. Maintain BigQuery SQL syntax compatibility
5. Focus on root causes, not symptoms (e.g., if column over-selection is the issue, add instruction to select only requested fields)

**Common Failure Patterns to Address:**
- Column over-selection (SELECT * instead of specific columns)
- Incorrect JOINs or missing JOINs
- Date filtering issues (wrong format, timezone handling)
- Aggregation errors (GROUP BY, COUNT, SUM, AVG)
- Missing WHERE clauses or incorrect filtering logic

**Output Format:**
Provide ONLY the improved prompt text without explanations or markdown formatting.
The output should be a direct replacement for the current prompt.
"""

        return prompt

    def present_suggestions_to_user(
        self,
        current_prompt: str,
        suggested_prompt: str
    ) -> Tuple[str, str]:
        """
        Present suggested prompt to user and get their decision.

        Args:
            current_prompt: Current prompt text
            suggested_prompt: Suggested improved prompt

        Returns:
            Tuple of:
                - final_prompt: Approved/edited prompt
                - change_description: User's description of changes
        """
        print(f"\n{'='*80}")
        print("PROMPT IMPROVEMENT SUGGESTION")
        print(f"{'='*80}\n")

        # Show diff
        self._show_diff(current_prompt, suggested_prompt)

        # Get user decision
        print(f"\n{'='*80}")
        print("Options:")
        print("  [a] Approve - Use suggested prompt as-is")
        print("  [e] Edit - Manually edit the suggested prompt")
        print("  [s] Skip - Keep current prompt, no changes")
        print(f"{'='*80}\n")

        while True:
            choice = input("Your choice (a/e/s): ").strip().lower()

            if choice == 'a':
                # Approve suggested prompt
                change_desc = input("\nDescribe the changes made (for tracking): ").strip()
                if not change_desc:
                    change_desc = "Applied AI-suggested improvements to address failures"
                return suggested_prompt, change_desc

            elif choice == 'e':
                # Edit suggested prompt
                print("\n=== Edit Prompt ===")
                print("Enter your edited prompt below. When done, enter '<<<END>>>' on a new line:\n")

                lines = []
                while True:
                    line = input()
                    if line.strip() == "<<<END>>>":
                        break
                    lines.append(line)

                edited_prompt = "\n".join(lines).strip()

                if not edited_prompt:
                    print("Empty prompt. Keeping suggested prompt.")
                    edited_prompt = suggested_prompt

                change_desc = input("\nDescribe the changes you made (for tracking): ").strip()
                if not change_desc:
                    change_desc = "User-edited prompt based on AI suggestions"

                return edited_prompt, change_desc

            elif choice == 's':
                # Skip - keep current prompt
                print("\nSkipping prompt update. Current prompt will be used.")
                return current_prompt, "No changes (skipped)"

            else:
                print("Invalid choice. Please enter 'a', 'e', or 's'.")

    def _show_diff(self, old_prompt: str, new_prompt: str):
        """
        Show side-by-side diff of old and new prompts.

        Args:
            old_prompt: Original prompt
            new_prompt: Suggested new prompt
        """
        print("CHANGES (unified diff):")
        print("-" * 80)

        old_lines = old_prompt.splitlines(keepends=True)
        new_lines = new_prompt.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="Current Prompt",
            tofile="Suggested Prompt",
            lineterm=""
        )

        diff_text = "".join(diff)
        if not diff_text:
            print("(No changes)")
        else:
            print(diff_text)

        print("-" * 80)

        # Show full suggested prompt
        print("\nFULL SUGGESTED PROMPT:")
        print("-" * 80)
        print(new_prompt)
        print("-" * 80)
