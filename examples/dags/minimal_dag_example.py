from airflow.decorators import dag, task
from datetime import datetime, timezone


@dag(
    dag_id="minimal_dag_example",
    schedule="@daily",
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["example"],
)
def minimal_dag():
    @task
    def hello_task():
        print("Hello Airflow 3")

    hello_task()


dag = minimal_dag()
