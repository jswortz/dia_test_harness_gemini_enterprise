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

    def __init__(self, project_id: str, location: str = "global", model_name: str = "gemini-3-pro-preview"):
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

    def analyze_failures(
        self,
        failures: List[Dict],
        current_prompt: str,
        successes: Optional[List[Dict]] = None,
        previous_metrics: Optional[Dict] = None
    ) -> str:
        """
        Analyze failure patterns and suggest prompt improvements.

        **CRITICAL: This method must ONLY receive TRAINING data to avoid data leakage.**
        All failures and successes MUST be from the training set. Test set data
        must NEVER be passed to this method.

        Args:
            failures: List of failed test cases FROM TRAINING SET ONLY
            current_prompt: Current NL2SQL prompt text
            successes: Optional list of successful test cases FROM TRAINING SET ONLY
            previous_metrics: Optional previous iteration metrics for trajectory analysis

        Returns:
            str: Suggested improved prompt
        """
        if not failures:
            print("No failures to analyze. Prompt is performing well!")
            return current_prompt

        print(f"\n=== Analyzing {len(failures)} Failures ===")
        if successes:
            print(f"Including {len(successes)} successful cases for pattern insights")
        if previous_metrics:
            print(f"Including previous iteration metrics for trajectory analysis")

        # Build analysis prompt for LLM with trajectory context
        analysis_prompt = self._build_analysis_prompt(failures, current_prompt, successes, previous_metrics)

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

    def _build_analysis_prompt(
        self,
        failures: List[Dict],
        current_prompt: str,
        successes: Optional[List[Dict]] = None,
        previous_metrics: Optional[Dict] = None
    ) -> str:
        """
        Build the prompt for LLM to analyze failures and suggest improvements.

        Args:
            failures: List of failed test cases
            current_prompt: Current NL2SQL prompt
            successes: Optional list of successful test cases
            previous_metrics: Optional previous iteration metrics for trajectory analysis

        Returns:
            str: Analysis prompt for LLM
        """
        # Build trajectory context section if previous metrics exist
        trajectory_context = ""
        if previous_metrics:
            # Extract accuracy from previous metrics (handle both dict and float formats)
            if isinstance(previous_metrics.get("accuracy"), dict):
                prev_accuracy = previous_metrics["accuracy"].get("mean", 0.0)
            else:
                prev_accuracy = previous_metrics.get("accuracy", 0.0)

            # Calculate current accuracy from failures and successes
            total = len(failures) + (len(successes) if successes else 0)
            current_correct = len(successes) if successes else 0
            current_accuracy = (current_correct / total * 100.0) if total > 0 else 0.0

            # Convert prev_accuracy to percentage if it's not already
            if prev_accuracy <= 1.0:
                prev_accuracy = prev_accuracy * 100.0

            # Check for regression
            if current_accuracy < prev_accuracy:
                delta = prev_accuracy - current_accuracy
                trajectory_context = f"""
**⚠️ CRITICAL: PERFORMANCE REGRESSION DETECTED**
- Previous iteration accuracy: {prev_accuracy:.2f}%
- Current iteration accuracy: {current_accuracy:.2f}%
- Regression: {delta:.2f}% (WORSE than before)

This iteration performed WORSE than the previous one. Your task is to:
1. Identify what changes in the prompt caused this regression
2. Suggest fixes that recover previous performance while addressing new failures
3. Consider recommending reverting recent changes if they were counterproductive
4. Balance fixing new failures without sacrificing previously working cases

**IMPORTANT**: The goal is to get back to at least {prev_accuracy:.2f}% accuracy.
"""
            else:
                # Improvement or same - provide positive context
                delta = current_accuracy - prev_accuracy
                trajectory_context = f"""
**📈 Trajectory Context:**
- Previous iteration accuracy: {prev_accuracy:.2f}%
- Current iteration accuracy: {current_accuracy:.2f}%
- Change: {delta:+.2f}% {'(improvement)' if delta > 0 else '(no change)'}

Continue improving while preserving what's working well.
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

        # Summarize successes (limit to 5 representative examples)
        success_text = ""
        if successes:
            success_summary = []
            # Sample up to 5 diverse successes
            sample_size = min(5, len(successes))
            sampled_successes = successes[:sample_size]

            for i, success in enumerate(sampled_successes, 1):
                summary = f"\n{i}. Question: \"{success.get('question', 'N/A')}\""
                summary += f"\n   Expected SQL: {success.get('expected_sql', 'N/A')}"
                summary += f"\n   Generated SQL: {success.get('generated_sql', 'N/A')}"
                success_summary.append(summary)

            success_text = f"""
**Successful Test Cases (showing what works well):**
{chr(10).join(success_summary)}

Use these successful patterns to understand what the agent is doing correctly and preserve those capabilities.
"""

        prompt = f"""You are an expert in prompt engineering for NL2SQL (Natural Language to SQL) systems.

I'm optimizing a Data Insights Agent that converts natural language questions into BigQuery SQL queries.

{trajectory_context}
**Current NL2SQL Prompt:**
```
{current_prompt}
```

**Failed Test Cases (TRAINING SET ONLY):**
{failures_text}
{success_text}
**Your Task:**
Analyze the TRAINING failure patterns and generate an IMPROVED version of the NL2SQL prompt that addresses these specific issues.

**IMPORTANT:** You are analyzing ONLY training set data. Do not make assumptions about test set performance.

**CRITICAL CONSTRAINTS FOR nl2sql_prompt FIELD:**

1. **FIELD PURPOSE:** nl2sql_prompt contains NATURAL LANGUAGE INSTRUCTIONS for how to generate SQL.
   - It should contain RULES, FORMULAS, GUIDELINES, and DECISION TREES
   - It should NOT be replaced with SQL code snippets or templates

2. **REQUIRED STRUCTURE:** The prompt MUST include these sections:
   - Table and join rules
   - Column naming conventions
   - Aggregation logic (when to GROUP BY)
   - Metric calculation formulas
   - Special query patterns
   - SQL validation guardrails

3. **FORBIDDEN CHANGES:**
   ❌ Replacing the entire prompt with SQL code snippets
   ❌ Reducing prompt size by more than 30%
   ❌ Removing existing instruction sections
   ❌ Converting instructions to executable code
   ❌ Replacing comprehensive rules with terse examples

4. **ALLOWED CHANGES:**
   ✅ Adding new instruction sections for newly identified patterns
   ✅ Clarifying ambiguous or incomplete rules
   ✅ Fixing incorrect formulas or logic
   ✅ Adding SQL examples to ILLUSTRATE rules (not replace them)
   ✅ Reorganizing sections for better clarity
   ✅ Expanding instructions with more specific guidance

5. **VALIDATION CHECKLIST (verify before returning):**
   - [ ] Prompt is LONGER or similar length (unless removing redundancy)
   - [ ] Contains instruction keywords: "MUST", "ALWAYS", "NEVER", "rule", "formula"
   - [ ] SQL keywords (SELECT, FROM, WHERE) are in examples, not as main content
   - [ ] All original sections are preserved or enhanced
   - [ ] New sections ADD to existing guidance, don't replace it

6. **IMPROVEMENT PATTERN:**
   When you see a failure:
   - Identify which RULE is missing or incomplete
   - ADD or ENHANCE that rule in the appropriate section
   - Provide SQL examples to ILLUSTRATE the rule
   - DO NOT replace the entire prompt with the example

**Guidelines:**
1. Keep the overall structure and tone of the original prompt
2. Add specific, actionable instructions to fix the identified issues
3. Add comprehensive rules - thorough instructions are better than terse ones
4. Maintain BigQuery SQL syntax compatibility
5. Focus on root causes, not symptoms (e.g., if column over-selection is the issue, add instruction to select only requested fields)
6. IMPORTANT: Preserve patterns from successful test cases - don't break what's already working

**Common Failure Patterns to Address:**
- Column over-selection (SELECT * instead of specific columns)
- Incorrect JOINs or missing JOINs
- Date filtering issues (wrong format, timezone handling)
- Aggregation errors (GROUP BY, COUNT, SUM, AVG)
- Missing WHERE clauses or incorrect filtering logic

**Output Format:**
Provide ONLY the improved prompt text without explanations or markdown formatting.
The output should be a direct replacement for the current prompt.
The output MUST be comprehensive natural language instructions, not SQL code.
"""

        return prompt

    def present_suggestions_to_user(
        self,
        current_prompt: str,
        suggested_prompt: str,
        auto_accept: bool = False
    ) -> Tuple[str, str]:
        """
        Present suggested prompt to user and get their decision.

        Args:
            current_prompt: Current prompt text
            suggested_prompt: Suggested improved prompt
            auto_accept: If True, automatically approve suggestions without user input

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

        # Auto-accept mode
        if auto_accept:
            print(f"\n{'='*80}")
            print("AUTO-ACCEPT MODE: Automatically approving AI suggestions")
            print(f"{'='*80}\n")
            return suggested_prompt, "Auto-approved AI-suggested improvements to address failures"

        # Manual approval mode
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
                print("Enter your edited prompt below. When done, enter 'END' on a new line:\n")

                lines = []
                while True:
                    line = input()
                    if line.strip() == "END":
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
