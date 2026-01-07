#!/usr/bin/env python3
"""
Analyze evaluation results and suggest prompt improvements using LLM judgment.
"""
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.evaluator import JudgementModel
from dotenv import load_dotenv

load_dotenv()


def load_results(results_file: str) -> list[dict]:
    """Load test results from JSONL file."""
    results = []
    with open(results_file, 'r') as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results


def analyze_patterns(results: list[dict]) -> dict:
    """Analyze patterns in the test results."""
    total = len(results)
    equivalent = sum(1 for r in results if 'EQUIVALENT' in r.get('explanation', ''))
    different = total - equivalent

    patterns = {
        'total_tests': total,
        'equivalent_count': equivalent,
        'different_count': different,
        'success_rate': (equivalent / total * 100) if total > 0 else 0,
        'issues': []
    }

    # Analyze common issues
    for result in results:
        if 'DIFFERENT' in result.get('explanation', ''):
            patterns['issues'].append({
                'question': result['question'],
                'expected_sql': result['expected_sql'],
                'generated_sql': result['generated_sql'],
                'explanation': result['explanation']
            })

    # Analyze syntactic differences even in equivalent queries
    fully_qualified_tables = 0
    verbose_aliasing = 0
    format_date_usage = 0
    count_column_vs_star = 0

    for result in results:
        gen_sql = result.get('generated_sql', '')
        if 'wortz-project-352116.dia_test_dataset' in gen_sql:
            fully_qualified_tables += 1
        if 'AS `_col_' in gen_sql or 'AS _col_' in gen_sql:
            verbose_aliasing += 1
        if 'FORMAT_DATE' in gen_sql:
            format_date_usage += 1
        if 'COUNT(`' in gen_sql and 'COUNT(*)' not in gen_sql:
            count_column_vs_star += 1

    patterns['syntactic_observations'] = {
        'fully_qualified_tables': fully_qualified_tables,
        'verbose_aliasing': verbose_aliasing,
        'format_date_usage': format_date_usage,
        'count_column_vs_star': count_column_vs_star
    }

    return patterns


def generate_prompt_recommendations(patterns: dict, judge: JudgementModel) -> str:
    """Use LLM to generate prompt improvement recommendations."""

    # Prepare analysis context
    analysis_context = f"""
I am analyzing the performance of a Data Insights Agent with the following baseline prompt:

"You are a specialized Data Scientist agent tasked with answering data-related questions
using BigQuery. When a user asks a question, generate the appropriate SQL query, execute
it, and provide a natural language response with the results."

**Test Results Summary:**
- Total tests: {patterns['total_tests']}
- Semantically equivalent: {patterns['equivalent_count']} ({patterns['success_rate']:.1f}%)
- Different/incorrect: {patterns['different_count']}

**Syntactic Observations (even in equivalent queries):**
- Fully qualified table names used: {patterns['syntactic_observations']['fully_qualified_tables']}/{patterns['total_tests']}
- Verbose column aliasing (e.g., AS _col_0): {patterns['syntactic_observations']['verbose_aliasing']}/{patterns['total_tests']}
- FORMAT_DATE vs BETWEEN for date filters: {patterns['syntactic_observations']['format_date_usage']} uses FORMAT_DATE
- COUNT(column) vs COUNT(*): {patterns['syntactic_observations']['count_column_vs_star']} use COUNT(column)

**Specific Issues Found:**
"""

    for i, issue in enumerate(patterns['issues'], 1):
        analysis_context += f"\n{i}. Question: \"{issue['question']}\"\n"
        analysis_context += f"   Expected SQL: {issue['expected_sql']}\n"
        analysis_context += f"   Generated SQL: {issue['generated_sql']}\n"
        analysis_context += f"   Issue: {issue['explanation']}\n"

    # Ask LLM for recommendations
    prompt = f"""{analysis_context}

Based on this analysis, please provide specific, actionable recommendations to improve
the agent's prompt. Focus on:

1. **Critical Issues**: Address the semantic differences that led to incorrect results
2. **SQL Style Guidance**: Should we guide the agent on table qualification, aliasing, etc.?
3. **Column Selection**: How to ensure the agent selects only requested columns
4. **Additional Context**: What examples or schema information might help?

Provide your recommendations in a structured format with clear priorities.
"""

    # Use the LLM model directly for recommendations
    try:
        response = judge.model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error generating recommendations: {str(e)}"


def main():
    results_file = 'results/golden_test_results.jsonl'

    if not os.path.exists(results_file):
        print(f"❌ Results file not found: {results_file}")
        print("Please run: python scripts/run_golden_test.py first")
        return

    print("=" * 70)
    print("PROMPT IMPROVEMENT ANALYSIS")
    print("=" * 70)
    print()

    # Load and analyze results
    print("Loading test results...")
    results = load_results(results_file)

    print("Analyzing patterns...")
    patterns = analyze_patterns(results)

    # Display summary
    print()
    print("=" * 70)
    print("TEST RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total tests: {patterns['total_tests']}")
    print(f"Semantically equivalent: {patterns['equivalent_count']} ({patterns['success_rate']:.1f}%)")
    print(f"Different/incorrect: {patterns['different_count']}")
    print()

    print("=" * 70)
    print("SYNTACTIC OBSERVATIONS")
    print("=" * 70)
    obs = patterns['syntactic_observations']
    print(f"Fully qualified table names: {obs['fully_qualified_tables']}/{patterns['total_tests']}")
    print(f"Verbose column aliasing: {obs['verbose_aliasing']}/{patterns['total_tests']}")
    print(f"FORMAT_DATE usage: {obs['format_date_usage']}/{patterns['total_tests']}")
    print(f"COUNT(column) vs COUNT(*): {obs['count_column_vs_star']}/{patterns['total_tests']}")
    print()

    if patterns['issues']:
        print("=" * 70)
        print(f"ISSUES FOUND ({len(patterns['issues'])} tests)")
        print("=" * 70)
        for i, issue in enumerate(patterns['issues'], 1):
            print(f"\n{i}. Question: \"{issue['question']}\"")
            print(f"   Expected: {issue['expected_sql']}")
            print(f"   Generated: {issue['generated_sql'][:100]}...")
            print(f"   Issue: {issue['explanation'][:200]}...")
        print()

    # Generate recommendations using LLM judge
    print("=" * 70)
    print("GENERATING PROMPT IMPROVEMENT RECOMMENDATIONS")
    print("=" * 70)
    print("Using Gemini LLM judge to analyze patterns and suggest improvements...")
    print()

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    location = os.getenv('DIA_LOCATION', 'global')
    judge = JudgementModel(project_id=project_id, location=location)
    recommendations = generate_prompt_recommendations(patterns, judge)

    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print(recommendations)
    print()

    # Save recommendations to file
    output_file = 'results/prompt_improvement_recommendations.txt'
    with open(output_file, 'w') as f:
        f.write("=" * 70 + "\n")
        f.write("PROMPT IMPROVEMENT RECOMMENDATIONS\n")
        f.write("Generated: " + str(patterns) + "\n")
        f.write("=" * 70 + "\n\n")
        f.write(recommendations)

    print(f"✓ Recommendations saved to: {output_file}")
    print()


if __name__ == '__main__':
    main()
