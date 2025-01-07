import pandas as pd

from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

from feast import Field, RequestSource
from feast.on_demand_feature_view import on_demand_feature_view
from feast.types import Float64, Int64
from feast import FeatureStore


store = FeatureStore(fs_yaml_file=Path("./feature_store.yaml"))
for e in store.list_all_feature_views():
    print(e.name)

driver_hourly_stats_view = store.get_feature_view("driver_hourly_stats")


entities = {
    "driver_id": [1001, 1002, 1003],
    "event_timestamp": [
        datetime(2021, 4, 12, 10, 59, 42),
        datetime(2021, 4, 12, 8, 12, 10),
        datetime(2021, 4, 12, 16, 40, 26),
    ],
    "label_driver_reported_satisfaction": [1, 5, 3],
    "val_to_add": [1, 2, 3],
    "val_to_add_2": [10, 20, 30],
}

entity_df = pd.DataFrame.from_dict(entities)

features = [
    "driver_hourly_stats:conv_rate",
    "driver_hourly_stats:acc_rate",
    "driver_hourly_stats:avg_daily_trips",
    "transformed_conv_rate:conv_rate_plus_val1",
    "transformed_conv_rate:conv_rate_plus_val2",
]

entity_rows = [
    {
        "driver_id": 1001,
        "val_to_add": 1,
        "val_to_add_2": 2,
    }
]

# print(store.list_on_demand_feature_views())

feature_service = store.get_feature_service("driver_activity_v3")
# print(feature_service)
online_response = store.get_online_features(
    entity_rows=entity_rows,
    # features=feature_service,
    features=[
        "driver_hourly_stats:conv_rate",
        "driver_hourly_stats:acc_rate",
    ],
).to_df()
print(online_response)

training_df = store.get_historical_features(entity_df, features).to_df()

store.materialize_incremental(end_date=datetime.now())  # results in NotImplementedError
store.materialize(
    start_date=datetime.fromisoformat("2019-01-01"), end_date=datetime.now()
)  # results in NotImplementedError

print("----- Feature schema -----\n")
training_df.info()

print()
print("-----  Features -----\n")
print(training_df.head())

print("------training_df----")

print(training_df)
