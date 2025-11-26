"""Example DAG demonstrating Airflow's task.virtualenv decorator."""

from datetime import datetime, timezone

from airflow.decorators import dag, task


@dag(
    dag_id="virtual_env_dag_example",
    schedule="@daily",
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["example", "virtualenv"],
)
def virtual_env_dag():
    @task.virtualenv(
        # python_version="3.12",  # Use whatever version your Airflow workers have
        requirements=[
            "pendulum",
        ],
    )
    def hello_task():
        import pendulum  # type: ignore

        now = pendulum.now("UTC").to_iso8601_string()
        print(f"Hello from an isolated virtualenv at {now}")

    hello_task()


dag = virtual_env_dag()
