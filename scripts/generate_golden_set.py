import json
import os
import uuid
import click

def generate_golden_set():
    """
    Generates a Golden Test Set with NL questions, expected SQL, and expected results pattern.
    Note: 'expected_result' here is a placeholder pattern or a specific value if determinable.
    For complex dynamic data, we might validates against the executed SQL result on the actual data.
    """
    golden_set = [
        {
            "question_id": str(uuid.uuid4()),
            "nl_question": "How many customers are there?",
            "complexity": "Simple",
            "expected_sql": "SELECT count(*) FROM `dataset.customers`",
            "sql_pattern": r"SELECT\s+count\(\*\)\s+FROM\s+`.*customers`",
            "expected_result_type": "INTEGER"
        },
        {
            "question_id": str(uuid.uuid4()),
            "nl_question": "List all product categories.",
            "complexity": "Simple",
            "expected_sql": "SELECT DISTINCT category FROM `dataset.products`",
            "sql_pattern": r"SELECT\s+DISTINCT\s+category\s+FROM\s+`.*products`",
            "expected_result_type": "STRING_LIST"
        },
        {
            "question_id": str(uuid.uuid4()),
            "nl_question": "Show me the total revenue for each status.",
            "complexity": "Medium",
            "expected_sql": "SELECT status, SUM(amount) as total_revenue FROM `dataset.orders` GROUP BY status",
            "sql_pattern": r"SELECT\s+status,\s+SUM\(amount\).*FROM\s+`.*orders`\s+GROUP\s+BY\s+status",
            "expected_result_type": "TABLE"
        },
        {
            "question_id": str(uuid.uuid4()),
            "nl_question": "What are the top 5 most expensive products?",
            "complexity": "Medium",
            "expected_sql": "SELECT name, price FROM `dataset.products` ORDER BY price DESC LIMIT 5",
            "sql_pattern": r"SELECT\s+name,\s+price\s+FROM\s+`.*products`\s+ORDER\s+BY\s+price\s+DESC\s+LIMIT\s+5",
            "expected_result_type": "TABLE"
        },
        {
            "question_id": str(uuid.uuid4()),
            "nl_question": "Find customers who placed orders in 2024.",
            "complexity": "Complex",
            "expected_sql": "SELECT DISTINCT c.name FROM `dataset.customers` c JOIN `dataset.orders` o ON c.id = o.customer_id WHERE o.order_date BETWEEN '2024-01-01' AND '2024-12-31'",
            "sql_pattern": r"SELECT\s+DISTINCT\s+.*FROM\s+`.*customers`.*JOIN\s+`.*orders`",
            "expected_result_type": "STRING_LIST"
        }
    ]
    return golden_set

@click.command()
@click.option('--output-file', default='data/golden_set.json', help='Output file path')
def main(output_file):
    """Generate Golden Test Set for DIA verification."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    data = generate_golden_set()
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    click.echo(f"Saved Golden Set with {len(data)} items to {output_file}")

if __name__ == '__main__':
    main()
