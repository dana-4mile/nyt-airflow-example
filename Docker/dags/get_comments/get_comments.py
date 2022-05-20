import requests
import json
import os
dirname = os.path.dirname(os.path.abspath(__file__))
import pendulum
import yaml

import sys
sys.path.append(f'{dirname}/../modules/')
from call_nyt_api import call_nyt_api
from ndjson import ndjsondumps

# GCS libraries

from google.cloud import storage

# Airflow libraries

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator

# from airflow.contrib.operators.bigquery_operator import BigQueryOperator


from airflow.hooks.base import BaseHook

# Load Config File

with open(f"{dirname}/dag_config.yaml", 'r') as config_yaml:
    dag_config=yaml.safe_load(config_yaml)
    # Airflow Config Variables:
    depends_on_past = dag_config["airflow_args"]["depends_on_past"]
    email = dag_config["airflow_args"]["email"]
    email_on_failure = dag_config["airflow_args"]["email_on_failure"]
    email_on_retry = dag_config["airflow_args"]["email_on_retry"]
    retries = dag_config["airflow_args"]["retries"]
    retry_delay = dag_config["airflow_args"]["retry_delay"]
    description = dag_config["airflow_args"]["description"]
    schedule_interval = dag_config["airflow_args"]["schedule_interval"]
    catchup = dag_config["airflow_args"]["catchup"]
    local_tz = pendulum.timezone(dag_config["airflow_args"]["local_tz"])
    start_year = dag_config["airflow_args"]["start_year"]
    start_month = dag_config["airflow_args"]["start_month"]
    start_day = dag_config["airflow_args"]["start_day"]
    start_hour = dag_config["airflow_args"]["start_hour"]
    start_date = pendulum.datetime(start_year, start_day, start_month, start_hour, tz=local_tz)
    max_active_runs = dag_config["airflow_args"]["max_active_runs"]
    # GCS Options:
    gcs_bucket = dag_config["gcs_args"]["gcs_bucket"]
    bq_project = dag_config["gcs_args"]["bq_project"]
    stg_dataset = dag_config["gcs_args"]["stg_dataset"]
    prod_dataset = dag_config["gcs_args"]["prod_dataset"]
    prod_table = dag_config["gcs_args"]["prod_table"]
    # API Config Variables:
    comments_endpoint = dag_config["api_args"]["comments_endpoint"]

with open(f'{dirname}/nyt_articles_schema.json', 'r') as schema:
    articles_schema = json.load(schema)

# Set API Key

# Local non-airflow Testing
# api_key = os.environ['NYT_SECRET']
connection = BaseHook.get_connection("nyt_secret")
api_key = connection.password

# Set GCS Credentials

os.environ["GOOGLE_APPLICATION_CREDENTIALS"]="/var/local/gcs_keyfile/gcs_keyfile.json"

# AirFlow TS:
# Local Testing:
# date_to_fetch = pendulum.now()

def call_articles_api(month,year):
    """Returns a JSONL string of articles for a given month"""
    endpoint = comments_endpoint.format(date_path=f"{year}/{month}")
    articles = call_nyt_api(endpoint, api_key, {})
    return articles

def get_articles(*args, **kwargs):
    """Python-Callable for Airflow. Uploads a JSONL file of one month of articles to a GCS Bucket"""
    date_to_fetch = kwargs['data_interval_start']
    articles = call_articles_api(date_to_fetch.month,date_to_fetch.year)["response"]["docs"]

    # delete a pesky duplicated field that BQ doesn't like trying to load JSONL
    for article in articles:
        for asset in article["multimedia"]:
            asset.pop('subType', None)

    ndarticles = ndjsondumps(articles)

    #create a storage client and upload to GCS
    storage_client = storage.Client()
    bucket = storage_client.bucket(gcs_bucket)
    fname = f"{date_to_fetch.format('YYYY[_]MM')}_articles.jsonl"
    blob = bucket.blob(fname)
    blob.upload_from_string(ndarticles)
    print(f"Uploaded file {fname} to bucket {gcs_bucket}")

# DAG Definition Begins:

with DAG(
    'get_articles_monthly',
    # These args will get passed on to each operator
    # You can override them on a per-task basis during operator initialization
    default_args={
        'depends_on_past': depends_on_past,
        'email': email,
        'email_on_failure': email_on_failure,
        'email_on_retry': email_on_retry,
        'retries': retries,
        'retry_delay': pendulum.duration(minutes=retry_delay)
    },
    description=description,
    schedule_interval=schedule_interval,
    start_date=start_date,
    catchup=catchup,
    max_active_runs=max_active_runs,
    user_defined_macros = {'bq_project': bq_project, 'stg_dataset': stg_dataset, 'prod_dataset': prod_dataset, 'prod_table': prod_table}
) as dag:

    fetch_articles = PythonOperator(
        task_id='fetch_articles_to_gcs',
        python_callable=get_articles,
    )

    gcs_to_bq_stage = GCSToBigQueryOperator(
        task_id='gcs_to_bq_stage',
        bucket=gcs_bucket,
        source_objects=["{{ data_interval_start.strftime('%Y_%m') }}_articles.jsonl"],
        source_format='NEWLINE_DELIMITED_JSON',
        destination_project_dataset_table=f"{bq_project}.{stg_dataset}.{{{{ data_interval_start.strftime('%Y_%m') }}}}_articles_stg",
        create_disposition='CREATE_IF_NEEDED',
        write_disposition='WRITE_TRUNCATE',
        schema_fields = articles_schema
    )

    bq_stage_to_prod = BigQueryInsertJobOperator(
    task_id="bq_stage_to_prod",
    configuration={
        "query": {
            "query": "{% include 'sql/insert_articles_to_prod.sql' %}",
            "useLegacySql": False,
        }
    },
    )

    fetch_articles >> gcs_to_bq_stage >> bq_stage_to_prod
