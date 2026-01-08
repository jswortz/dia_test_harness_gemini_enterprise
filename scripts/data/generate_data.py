import csv
import json
import random
import os
from datetime import datetime, timedelta
from faker import Faker
import click

fake = Faker()

def generate_customers(num_customers):
    customers = []
    for _ in range(num_customers):
        customers.append({
            "id": fake.uuid4(),
            "name": fake.name(),
            "email": fake.email(),
            "region": fake.state(),
            "signup_date": fake.date_between(start_date="-2y", end_date="today").isoformat()
        })
    return customers

def generate_products(num_products):
    categories = ["Electronics", "Clothing", "Home & Garden", "Books", "Toys"]
    products = []
    for _ in range(num_products):
        price = round(random.uniform(10, 500), 2)
        products.append({
            "id": fake.uuid4(),
            "name": fake.catch_phrase(),
            "category": random.choice(categories),
            "price": price,
            "cost": round(price * random.uniform(0.5, 0.8), 2)
        })
    return products

def generate_orders(num_orders, customers, products):
    orders = []
    order_items = []
    
    for _ in range(num_orders):
        order_id = fake.uuid4()
        customer = random.choice(customers)
        order_date = fake.date_between(start_date="-1y", end_date="today")
        
        orders.append({
            "id": order_id,
            "customer_id": customer["id"],
            "order_date": order_date.isoformat(),
            "status": random.choice(["SHIPPED", "PENDING", "DELIVERED", "CANCELLED"]),
            "amount": 0 # Will be calculated
        })
        
        # items
        total_amount = 0
        num_items = random.randint(1, 5)
        for _ in range(num_items):
            product = random.choice(products)
            quantity = random.randint(1, 3)
            total_amount += product["price"] * quantity
            
            order_items.append({
                "id": fake.uuid4(),
                "order_id": order_id,
                "product_id": product["id"],
                "quantity": quantity,
                "price_at_purchase": product["price"]
            })
            
        orders[-1]["amount"] = round(total_amount, 2)
        
    return orders, order_items

def generate_all_data(customers, products, orders, output_dir):
    """Generate and save all data."""
    os.makedirs(output_dir, exist_ok=True)
    
    click.echo(f"Generating {customers} customers...")
    customer_data = generate_customers(customers)
    
    click.echo(f"Generating {products} products...")
    product_data = generate_products(products)
    
    click.echo(f"Generating {orders} orders...")
    order_data, order_item_data = generate_orders(orders, customer_data, product_data)
    
    # Save to JSON (newline delimited for BQ)
    files = {
        "customers.json": customer_data,
        "products.json": product_data,
        "orders.json": order_data,
        "order_items.json": order_item_data
    }
    
    for filename, data in files.items():
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w') as f:
            for item in data:
                f.write(json.dumps(item) + '\n')
        click.echo(f"Saved {filename} to {output_dir}")

@click.command()
@click.option('--customers', default=100, help='Number of customers')
@click.option('--products', default=50, help='Number of products')
@click.option('--orders', default=500, help='Number of orders')
@click.option('--output-dir', default='data', help='Output directory')
def main(customers, products, orders, output_dir):
    """Generate fake E-commerce data for BigQuery."""
    generate_all_data(customers, products, orders, output_dir)

if __name__ == '__main__':
    main()
