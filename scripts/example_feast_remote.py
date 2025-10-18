"""Example demonstrating how to consume a remote-backed Feast deployment."""

from __future__ import annotations
import os
from datetime import UTC, datetime, timedelta
from typing import cast

import pandas as pd

from feast.types import Float64, Int64
from feast.data_source import PushMode, PushSource
from feast import Entity, FeatureService, FeatureStore, FeatureView, Field, ValueType

# try:  # Feast < 0.55
from feast.infra.offline_stores.contrib.postgres_offline_store.postgres import (
    PostgreSQLOfflineStoreConfig as PostgresOfflineStoreConfig,
)
# except ImportError:  # pragma: no cover - newer Feast
#     from feast.infra.offline_stores.contrib.postgres_offline_store.config import (
#         PostgresOfflineStoreConfig,
#     )

from feast.infra.offline_stores.contrib.postgres_offline_store.postgres_source import (
    PostgreSQLSource,
)

from mlox.services.feast.client import (
    cleanup_repo_config,
    get_repo_config,
)


DEMO_TABLE_NAME = "mlox_demo_driver_hourly_stats"
DEMO_ENTITY_NAME = "mlox_demo_driver"
DEMO_FEATURE_VIEW_NAME = "mlox_demo_driver_hourly_stats"
DEMO_FEATURE_SERVICE_NAME = "mlox_demo_driver_activity"

SAMPLE_DRIVER_ROWS = pd.DataFrame(
    {
        "driver_id": [101, 102, 103],
        "event_timestamp": [
            datetime(2024, 6, 1, 10, 0, tzinfo=UTC),
            datetime(2024, 6, 1, 11, 0, tzinfo=UTC),
            datetime(2024, 6, 1, 12, 30, tzinfo=UTC),
        ],
        "created": [
            datetime(2024, 6, 1, 10, 5, tzinfo=UTC),
            datetime(2024, 6, 1, 11, 3, tzinfo=UTC),
            datetime(2024, 6, 1, 12, 35, tzinfo=UTC),
        ],
        "conv_rate": [0.83, 0.74, 0.81],
        "acc_rate": [0.91, 0.87, 0.92],
        "avg_daily_trips": [96, 88, 104],
    }
)


def _register_demo_definitions(store: FeatureStore) -> FeatureService:
    offline_cfg = store.config.offline_store
    if not isinstance(offline_cfg, PostgresOfflineStoreConfig):
        raise RuntimeError(
            "Expected Postgres offline store configuration when running the remote example."
        )
    offline_cfg = cast(PostgresOfflineStoreConfig, offline_cfg)

    # entity
    driver_entity = Entity(
        name=DEMO_ENTITY_NAME,
        join_keys=["driver_id"],
        description="Demo driver entity used for Feast remote example.",
        value_type=ValueType.INT64,
    )

    # data source
    source_kwargs = {
        "name": f"{DEMO_FEATURE_VIEW_NAME}_source",
        "table": DEMO_TABLE_NAME,
        "timestamp_field": "event_timestamp",
        "created_timestamp_column": "created",
    }
    stats_source = PostgreSQLSource(**source_kwargs)

    push_source = PushSource(
        name="mlox_demo_driver_stats_push",
        batch_source=stats_source,
    )

    # feature view
    feature_view_kwargs = {
        "name": DEMO_FEATURE_VIEW_NAME,
        "entities": [driver_entity],
        "ttl": timedelta(days=1),
        "schema": [
            Field(name="conv_rate", dtype=Float64),
            Field(name="acc_rate", dtype=Float64),
            Field(name="avg_daily_trips", dtype=Int64),
        ],
        "online": True,
        "offline": False,
        "tags": {"source": "postgres", "demo": "mlox"},
        "source": push_source,
    }
    driver_hourly_stats = FeatureView(**feature_view_kwargs)

    driver_activity_service = FeatureService(
        name=DEMO_FEATURE_SERVICE_NAME,
        features=[driver_hourly_stats],
        tags={"demo": "remote-postgres"},
    )

    store.apply(
        [driver_entity, push_source, driver_hourly_stats, driver_activity_service]
    )
    store.refresh_registry()

    store.push(
        "mlox_demo_driver_stats_push",
        SAMPLE_DRIVER_ROWS,
        to=PushMode.ONLINE,
    )
    return driver_activity_service


def run_demo(service_name: str = "feast-0.54.0") -> None:
    key = os.environ.get("MLOX_FEAST_KEYFILE", "")
    pw = os.environ.get("MLOX_FEAST_PW", "")
    repo_config, tmpdir = get_repo_config(service_name, key, pw)
    try:
        # feature_store = FeatureStore(fs_yaml_file=tmpdir / "feature_store.yaml")
        feature_store = FeatureStore(config=repo_config)
        feature_service = _register_demo_definitions(feature_store)

        print("Feature store config loaded from:", tmpdir / "feature_store.yaml")
        print("Project name:", feature_store.project)
        print("Registered feature service:", feature_service.name)

        entity_df = pd.DataFrame(
            {
                "driver_id": [999, 101, 102],
                "event_timestamp": [pd.Timestamp("2024-06-01T00:00:00Z")] * 3,
            }
        )
        historical = feature_store.get_historical_features(
            entity_df=entity_df,
            features=[
                f"{DEMO_FEATURE_VIEW_NAME}:conv_rate",
                f"{DEMO_FEATURE_VIEW_NAME}:acc_rate",
            ],
        ).to_df()
        print("Historical features:\n", historical.head())

        # feature_store.materialize_incremental(end_date=datetime.now(tz=UTC))
        # feature_store.materialize(
        #     start_date=datetime(2024, 6, 1, tzinfo=UTC), end_date=datetime.now(tz=UTC)
        # )
        online = feature_store.get_online_features(
            features=feature_service,
            entity_rows=[
                {"driver_id": 999},
                {"driver_id": 101},
                {"driver_id": 102},
            ],
        ).to_df()
        print("Online features:\n", online.head())
    finally:
        print("Cleaning up temporary directory:", tmpdir)
        cleanup_repo_config(tmpdir)


if __name__ == "__main__":
    run_demo()
