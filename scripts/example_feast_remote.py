"""Example demonstrating how to consume a remote-backed Feast deployment."""

from __future__ import annotations

import os
import shutil
from datetime import datetime

import pandas as pd
from feast import FeatureStore

from mlox.services.feast.client import materialize_feature_store_config
from mlox.session import MloxSession


def run_demo(service_name: str = "feast-latest") -> None:
    password = os.environ.get("MLOX_CONFIG_PASSWORD")
    if not password:
        raise RuntimeError("MLOX_CONFIG_PASSWORD environment variable is not set.")

    session = MloxSession("mlox", password)
    tmpdir = materialize_feature_store_config(session.infra, service_name)
    try:
        feature_store = FeatureStore(fs_yaml_file=tmpdir / "feature_store.yaml")
        views = [view.name for view in feature_store.list_all_feature_views()]
        print("Available feature views:", views)

        feature_service = feature_store.get_feature_service("driver_activity_v3")
        print("Feature service:", feature_service.name)

        entity_df = pd.DataFrame(
            {
                "driver_id": [1001, 1002],
                "event_timestamp": [datetime.utcnow()] * 2,
            }
        )
        historical = feature_store.get_historical_features(
            entity_df,
            features=[
                "driver_hourly_stats:conv_rate",
                "driver_hourly_stats:acc_rate",
            ],
        ).to_df()
        print("Historical features:\n", historical.head())
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    run_demo()
