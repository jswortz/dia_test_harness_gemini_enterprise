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

    def __init__(self, project_id: str, location: str = "global", model_name: str = "gemini-3-pro-preview", temperature: float = 1.0):
        """
        Initialize prompt improver.

        Args:
            project_id: Google Cloud project ID
            location: Location for Vertex AI (e.g., "global", "us-central1")
            model_name: Gemini model to use for analysis
            temperature: Sampling temperature (0.0-2.0). Default 1.0 per OPRO research.
                        - 0.0-0.5: Conservative, less diverse suggestions
                        - 1.0: Balanced exploration-exploitation (OPRO optimal)
                        - 1.5-2.0: Creative but potentially random
        """
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self.temperature = temperature

        # Initialize Vertex AI
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel(model_name)

    def analyze_failures(
        self,
        failures: List[Dict],
        current_prompt: str,
        successes: Optional[List[Dict]] = None,
        previous_metrics: Optional[Dict] = None,
        trajectory_history: Optional[List[Dict]] = None
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
            previous_metrics: Optional previous iteration metrics (deprecated, use trajectory_history)
            trajectory_history: Optional full trajectory history (OPRO-aligned approach)

        Returns:
            str: Suggested improved prompt
        """
        if not failures:
            print("No failures to analyze. Prompt is performing well!")
            return current_prompt

        print(f"\n=== Analyzing {len(failures)} Failures ===")
        if successes:
            print(f"Including {len(successes)} successful cases for pattern insights")
        if trajectory_history:
            print(f"Including full trajectory history ({len(trajectory_history)} iterations) for OPRO-aligned optimization")
        elif previous_metrics:
            print(f"Including previous iteration metrics for trajectory analysis (legacy mode)")

        # Build analysis prompt for LLM with trajectory context
        analysis_prompt = self._build_analysis_prompt(failures, current_prompt, successes, previous_metrics, trajectory_history)

        # Generate suggestions with OPRO-aligned temperature
        print(f"Generating prompt improvement suggestions (temperature={self.temperature})...")
        from vertexai.generative_models import GenerationConfig

        generation_config = GenerationConfig(
            temperature=self.temperature,
            top_p=1.0,
            top_k=40,
            max_output_tokens=8192
        )

        response = self.model.generate_content(
            analysis_prompt,
            generation_config=generation_config
        )
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
                extracted = "\n".join(prompt_lines).strip()

                # CRITICAL VALIDATION: Ensure extracted content is instructions, not SQL code
                # If extraction starts with SQL keywords, it's likely wrong - use full response
                if not extracted.upper().startswith(('SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'FROM', 'JOIN', 'WHERE', 'INNER', 'LEFT', 'RIGHT')):
                    suggested_prompt = extracted
                else:
                    # SQL code detected in code block - don't extract, use full response
                    print(f"⚠️  Warning: Code block contains SQL, not instructions. Using full response.")

        # Final validation: Ensure we didn't extract SQL code
        if suggested_prompt.strip().upper().startswith(('SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'FROM', 'JOIN', 'INNER', 'LEFT', 'RIGHT')):
            print(f"🔴 ERROR: Extracted prompt appears to be SQL code, not instructions!")
            print(f"   Preview: {suggested_prompt[:200]}")
            print(f"   Returning current prompt instead to prevent corruption.")
            return current_prompt  # Return original to prevent corruption

        # CRITICAL SAFETY CHECK: Validate prompt meets minimum requirements
        validation_result = self._validate_prompt_quality(suggested_prompt, current_prompt)
        if not validation_result["valid"]:
            print(f"🔴 ERROR: Prompt validation failed!")
            for reason in validation_result["reasons"]:
                print(f"   - {reason}")
            print(f"   Returning current prompt instead to prevent corruption.")
            return current_prompt

        return suggested_prompt

    def _validate_prompt_quality(
        self,
        suggested_prompt: str,
        current_prompt: str
    ) -> Dict[str, Any]:
        """
        Validate that suggested prompt meets quality requirements.

        Critical safety checks to prevent prompt corruption.

        Args:
            suggested_prompt: The suggested new prompt
            current_prompt: The current prompt (for comparison)

        Returns:
            Dict with:
                - valid (bool): Whether prompt passes validation
                - reasons (List[str]): List of validation failure reasons
        """
        reasons = []

        # VALIDATION 1: Minimum length (prevent replacement with snippets)
        MIN_PROMPT_LENGTH = 1000  # chars
        if len(suggested_prompt) < MIN_PROMPT_LENGTH:
            reasons.append(
                f"Prompt too short: {len(suggested_prompt)} chars "
                f"(minimum: {MIN_PROMPT_LENGTH})"
            )

        # VALIDATION 2: Prevent drastic size reduction (>40% shrinkage)
        # CONSERVATIVE APPROACH: Prefer prompts to GROW, not shrink
        if len(current_prompt) > 0:
            size_ratio = len(suggested_prompt) / len(current_prompt)
            shrinkage_pct = (1 - size_ratio) * 100

            if size_ratio < 0.6:  # More than 40% reduction - REJECT
                reasons.append(
                    f"Prompt shrunk by {shrinkage_pct:.0f}% "
                    f"({len(current_prompt)} -> {len(suggested_prompt)} chars). "
                    f"Maximum allowed reduction is 40%. "
                    f"This often indicates over-correction that breaks working queries."
                )
            elif size_ratio < 0.85:  # 15-40% reduction - WARNING
                # Don't reject, but log warning
                import logging
                logging.warning(
                    f"⚠️  Prompt shrinkage detected: {shrinkage_pct:.0f}% reduction. "
                    f"Conservative approach prefers additions over deletions."
                )

        # VALIDATION 3: Must contain instruction keywords (not just code)
        instruction_keywords = ['MUST', 'ALWAYS', 'NEVER', 'should', 'rule', 'formula', 'when', 'if']
        keyword_count = sum(1 for kw in instruction_keywords if kw.lower() in suggested_prompt.lower())

        if keyword_count < 3:
            reasons.append(
                f"Missing instruction keywords. Found {keyword_count}, need at least 3 from: "
                f"{', '.join(instruction_keywords)}"
            )

        # VALIDATION 4: SQL keywords should not dominate (indicates code, not instructions)
        sql_keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'GROUP BY', 'ORDER BY', 'HAVING']
        sql_count = sum(suggested_prompt.upper().count(kw) for kw in sql_keywords)

        # Allow SQL in examples, but not as majority of content
        # Heuristic: SQL keywords should not appear more than once per 100 chars
        sql_density = sql_count / (len(suggested_prompt) / 100)
        if sql_density > 5:  # More than 5 SQL keywords per 100 chars
            reasons.append(
                f"Too many SQL keywords ({sql_count} in {len(suggested_prompt)} chars). "
                f"This suggests SQL code, not natural language instructions."
            )

        # VALIDATION 5: Check for required sections/patterns
        # A proper prompt should have multiple lines and paragraphs
        line_count = len(suggested_prompt.split('\n'))
        if line_count < 10:
            reasons.append(
                f"Prompt has only {line_count} lines. "
                f"Comprehensive instructions should have at least 10 lines."
            )

        # VALIDATION 6: Check for role/behavior preservation
        # Detect if agent role was changed inappropriately
        role_change_indicators = [
            'code generator',
            'sql generator',
            'output format: sql only',
            'no commentary',
            'do not provide explanations',
            'generation only',
            'not a database interface',
            'output must be only'
        ]

        found_indicators = [
            indicator for indicator in role_change_indicators
            if indicator.lower() in suggested_prompt.lower()
        ]

        if found_indicators and len(current_prompt) > 0:
            # Check if these weren't in the original
            original_had_indicators = any(
                indicator.lower() in current_prompt.lower()
                for indicator in found_indicators
            )

            if not original_had_indicators:
                reasons.append(
                    f"Role/behavior change detected. Found new restrictions: {', '.join(found_indicators)}. "
                    f"This violates PRINCIPLE 5: preserve agent role and conversational capabilities."
                )

        return {
            "valid": len(reasons) == 0,
            "reasons": reasons
        }

    def _build_analysis_prompt(
        self,
        failures: List[Dict],
        current_prompt: str,
        successes: Optional[List[Dict]] = None,
        previous_metrics: Optional[Dict] = None,
        trajectory_history: Optional[List[Dict]] = None
    ) -> str:
        """
        Build the prompt for LLM to analyze failures and suggest improvements.

        Args:
            failures: List of failed test cases
            current_prompt: Current NL2SQL prompt
            successes: Optional list of successful test cases
            previous_metrics: Optional previous iteration metrics (deprecated)
            trajectory_history: Optional full trajectory history (OPRO-aligned)

        Returns:
            str: Analysis prompt for LLM
        """
        # Build OPRO-aligned trajectory context section if trajectory_history exists
        trajectory_context = ""
        if trajectory_history and len(trajectory_history) > 0:
            # OPRO approach: Show all past (prompt, score) pairs sorted ascending
            trajectory_lines = ["**🎯 Optimization Trajectory (Past Prompts Sorted by Accuracy)**\n"]
            trajectory_lines.append("The following prompts were tried in previous iterations, sorted from WORST to BEST performing:")
            trajectory_lines.append("(Best prompts are at the END - learn from their patterns)\n")

            for idx, item in enumerate(trajectory_history, 1):
                preview = item.get("prompt_preview", "")
                accuracy = item.get("accuracy", 0.0)
                iteration = item.get("iteration", 0)

                trajectory_lines.append(f"\n{idx}. **Iteration {iteration}** → Accuracy: {accuracy:.2f}%")
                trajectory_lines.append(f"   Prompt preview: \"{preview}\"")

            # Add goal statement
            best_accuracy = trajectory_history[-1].get("accuracy", 0.0) if trajectory_history else 0.0
            trajectory_lines.append(f"\n**Your Goal**: Generate a NEW prompt that achieves HIGHER accuracy than {best_accuracy:.2f}%.")
            trajectory_lines.append("Analyze patterns in high-scoring prompts above and improve upon them.")
            trajectory_lines.append("Focus on what makes the best-performing prompts effective.\n")

            trajectory_context = "\n".join(trajectory_lines)

        elif previous_metrics:
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

                # Extract rubric score if available (format: "Total: X/25")
                import re
                score_match = re.search(r'Total[:\s]+(\d+)/25', failure['explanation'], re.IGNORECASE)
                if score_match:
                    score = int(score_match.group(1))
                    severity = "CRITICAL" if score < 10 else "MODERATE" if score < 20 else "MINOR"
                    summary += f"\n   Severity: {severity} (score: {score}/25)"
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
   ❌ **REMOVING instructions that help successful test cases**
   ❌ **CHANGING the agent's core role or personality** (e.g., analyst → code generator)
   ❌ **CHANGING output format** (e.g., adding "SQL only, no commentary" restrictions)
   ❌ **REMOVING conversational/explanatory capabilities**

4. **ALLOWED CHANGES:**
   ✅ Adding new instruction sections for newly identified patterns
   ✅ Clarifying ambiguous or incomplete rules
   ✅ Fixing incorrect formulas or logic
   ✅ Adding SQL examples to ILLUSTRATE rules (not replace them)
   ✅ Reorganizing sections for better clarity
   ✅ Expanding instructions with more specific guidance

**🚨 CRITICAL: CONSERVATIVE APPROACH REQUIRED**

You MUST follow these principles to avoid breaking working queries:

**PRINCIPLE 1: ADD, DON'T REPLACE**
- Default action: ADD new rules/clarifications to existing prompt
- NEVER remove entire sections unless they directly contradict correct behavior
- If a rule seems incomplete, EXPAND it rather than delete it
- Preserve ALL working instructions even if they seem redundant

**PRINCIPLE 2: PRESERVE SUCCESSFUL PATTERNS**
- Review the successful test cases carefully
- Identify which prompt instructions enabled those successes
- PROTECT those instructions from modification
- Only modify instructions if they clearly cause failures AND don't help successes

**PRINCIPLE 3: TARGETED FIXES ONLY**
- Address SPECIFIC failure root causes
- Don't make broad changes that might affect unrelated queries
- If fixing one pattern, verify it won't break another
- Prefer adding clarifying notes over changing existing rules

**PRINCIPLE 4: SIZE PRESERVATION**
- Aim for prompt to stay SAME SIZE or GROW (additions > deletions)
- If you must delete something, replace it with better guidance of similar length
- Shrinking the prompt is a RED FLAG - it often indicates removing helpful content

**PRINCIPLE 5: PRESERVE CORE AGENT ROLE & BEHAVIOR**
- NEVER change the agent's fundamental role or personality
- NEVER change output format expectations (conversational vs code-only)
- NEVER switch paradigms (e.g., "data analyst" → "code generator")
- NEVER add instructions like "OUTPUT FORMAT: SQL only, no commentary"
- NEVER add "you are a code generator, not a database interface"
- Preserve conversational/explanatory capabilities
- The agent should EXPLAIN results, not just generate code
- Focus on improving SQL QUALITY, not changing how the agent communicates

**EXAMPLE OF GOOD VS BAD CHANGES:**

❌ BAD: "The current prompt tells agents to include context columns. I'll remove that since some failures have too many columns."
✅ GOOD: "The current prompt tells agents to include context columns. I'll ADD guidance about WHEN to include them and which ones are essential vs optional."

❌ BAD: "I'll simplify the date handling section since it's too complex."
✅ GOOD: "I'll ADD specific examples to the date handling section to clarify edge cases."

❌ BAD: "Iteration had 5 failures. I'll rewrite the prompt to fix all 5."
✅ GOOD: "Iteration had 5 failures and 12 successes. I'll ADD targeted rules for the 5 failures while preserving what makes the 12 successes work."

❌ BAD: "The agent is generating conversational responses. I'll change it to a pure code generator that outputs SQL only."
✅ GOOD: "The agent's SQL has some issues. I'll ADD rules to improve SQL quality while keeping the conversational explanation capability."

❌ BAD: "I'll add 'OUTPUT FORMAT: SQL in markdown only, no commentary' to make it cleaner."
✅ GOOD: "I'll ADD specific SQL quality rules (join syntax, aggregation logic) to improve accuracy."

5. **VALIDATION CHECKLIST (verify before returning):**
   - [ ] Prompt is LONGER or similar length (unless removing redundancy)
   - [ ] Prompt size doesn't shrink by more than 20% in a single iteration
   - [ ] Contains instruction keywords: "MUST", "ALWAYS", "NEVER", "rule", "formula"
   - [ ] SQL keywords (SELECT, FROM, WHERE) are in examples, not as main content
   - [ ] All original sections are preserved or enhanced
   - [ ] New sections ADD to existing guidance, don't replace it
   - [ ] Context/supporting column instructions are preserved unless failures prove them harmful

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
5. Focus on root causes, not symptoms. Preserve helpful patterns unless they're directly causing failures.
6. IMPORTANT: Preserve patterns from successful test cases - don't break what's already working

**CRITICAL: Preserve What Works**
- If the current prompt instructs to include context/supporting columns (like guest_counts, days_in_period, period labels), preserve this unless there's clear evidence it's causing failures
- Adding analytical context columns is often beneficial for query accuracy
- Only remove or restrict column selection instructions if the failures explicitly show they're causing problems
- Do not interpret helpful context columns as "over-selection"

**Common Failure Patterns to Address:**
- Selecting unnecessary columns that significantly slow queries (e.g., SELECT * on wide tables)
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
