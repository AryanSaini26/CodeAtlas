from airflow import DAG


with DAG("daily_orders") as dag:
    extract_orders = object(task_id="extract_orders")
    build_ltv = object(task_id="build_customer_ltv")
