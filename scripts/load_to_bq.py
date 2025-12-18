import os
import json
import click
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

from dotenv import load_dotenv

load_dotenv()

def load_all_files(project, dataset, data_dir):
    """Load generated JSON data into BigQuery."""
    client = bigquery.Client(project=project)
    dataset_id = f"{project}.{dataset}"
    
    # Create Dataset
    try:
        client.get_dataset(dataset_id)
        click.echo(f"Dataset {dataset_id} already exists.")
    except NotFound:
        ds = bigquery.Dataset(dataset_id)
        ds.location = os.environ.get("BQ_GOOGLE_CLOUD_LOCATION", "US")
        client.create_dataset(ds, timeout=30)
        click.echo(f"Created dataset {dataset_id}")

    # Files to load and their schemas
    files_to_load = {
        "customers.json": "customers",
        "products.json": "products",
        "orders.json": "orders",
        "order_items.json": "order_items"
    }
    
    for filename, table_name in files_to_load.items():
        file_path = os.path.join(data_dir, filename)
        if not os.path.exists(file_path):
            click.epilog(f"Warning: {file_path} not found. Skipping.")
            continue
            
        table_id = f"{dataset_id}.{table_name}"
        
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            autodetect=True,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        
        with open(file_path, "rb") as source_file:
            job = client.load_table_from_file(source_file, table_id, job_config=job_config)
            
        job.result()  # Waits for the job to complete.
        
        table = client.get_table(table_id)
        click.echo(f"Loaded {table.num_rows} rows into {table_id}.")

@click.command()
@click.option('--project', default=os.environ.get("GOOGLE_CLOUD_PROJECT"), help='Google Cloud Project ID')
@click.option('--dataset', default=os.environ.get("BQ_DATASET_ID", "dia_test_dataset"), help='BigQuery Dataset ID (will be created if not exists)')
@click.option('--data-dir', default='data', help='Directory containing JSON data files')
def main(project, dataset, data_dir):
    if not project:
        raise click.ClickException("Project ID is required. Set GOOGLE_CLOUD_PROJECT or pass --project.")
    load_all_files(project, dataset, data_dir)

if __name__ == '__main__':
    main()
