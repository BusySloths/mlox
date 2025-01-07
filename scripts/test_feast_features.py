import pandas as pd

from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

from feast import Field, RequestSource
from feast.on_demand_feature_view import on_demand_feature_view
from feast.types import Float64, Int64
from feast import FeatureStore, FeatureView, FeatureService


# store = FeatureStore(repo_path=".")
store = FeatureStore(fs_yaml_file=Path("./feature_store.yaml"))

print("All feature views: ")
for e in store.list_all_feature_views():
    print(" -", e.name)

print("On demand feature views: ")
for e in store.list_on_demand_feature_views():
    print(" -", e.name, e.write_to_online_store)

print("Feature Services: ")
for es in store.list_feature_services():
    proj = es.feature_view_projections
    print(" -", es.name, [p.name for p in proj])

fv = store.get_feature_view("driver_hourly_stats")
fs = FeatureService(
    name="MySimpleFeatureService",
    features=[fv],
    tags={"tag1": "tagValue1"},
    description="My Description",
    owner="abc@def.de",
)
store.apply(fs)

print(fv.entities)

res = store.get_online_features(fs, entity_rows=[{"driver": 1001}]).to_df()
print(res)
