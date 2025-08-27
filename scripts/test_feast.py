import os
import yaml
import pandas as pd
import shutil

from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, TYPE_CHECKING

from mlox.services.feast.docker import FeastDockerService  # pragma: no cover


from feast import Field, RequestSource
from feast.on_demand_feature_view import on_demand_feature_view
from feast.types import Float64, Int64
from feast import FeatureStore, RepoConfig

from mlox.session import MloxSession


def setup_feast_config(service: FeastDockerService) -> Path:
    """Create a temporary directory containing a Feast certificate and a
    minimal `test_feature_store.yaml` configured from the provided
    FeastDockerService instance.

    Returns the Path to the temporary directory.
    """
    import tempfile
    from urllib.parse import urlparse

    tmpdir = Path(tempfile.mkdtemp(prefix="mlox_feast_"))

    # write certificate
    cert_text = service.certificate
    cert_path = tmpdir / "feast_crt.pem"
    cert_path.write_text(cert_text)

    # Derive host and ports from service attributes
    registry_url = None
    if hasattr(service, "service_urls") and isinstance(service.service_urls, dict):
        registry_url = service.service_urls.get("Feast")
    if not registry_url:
        registry_url = getattr(service, "service_url", None)

    parsed = urlparse(registry_url) if registry_url else None
    host = parsed.hostname if parsed and parsed.hostname else None

    # Fallback: try to parse host from plain service_url string
    if not host and isinstance(registry_url, str) and "://" in registry_url:
        try:
            host = registry_url.split("://", 1)[1].split(":")[0]
        except Exception:
            host = registry_url

    # ports
    ports = getattr(service, "service_ports", {}) or {}
    registry_port = ports.get("registry") or (parsed.port if parsed else None)
    online_port = ports.get("online_store")
    offline_port = ports.get("offline_store")

    yaml_dict = {
        "project": "my_project",
        "provider": "local",
        "entity_key_serialization_version": 3,
        "auth": {"type": "no_auth"},
        "registry": {
            "registry_type": "remote",
            "path": f"{host}:{registry_port}",
        },
        "online_store": {
            "type": "remote",
            "path": f"https://{host}:{online_port}",
        },
        "offline_store": {
            "type": "remote",
            "host": host,
            "port": offline_port,
        },
    }
    yaml_content = yaml.dump(yaml_dict)
    (tmpdir / "local_feature_store.yaml").write_text(yaml_content)
    return tmpdir


def teardown_feast_config(path: Path) -> None:
    """Remove the temporary directory created by setup_feast_config.

    Safe to call with a Path or string; missing paths are ignored.
    """
    try:
        if not path:
            return
        p = Path(path)
        if p.exists():
            shutil.rmtree(p)
    except Exception:
        # Best effort cleanup; avoid raising during teardown
        pass


# --- DATABASE CONNECTION PARAMETERS ---
# These parameters can be set directly in this script or, for better security,
# as environment variables on your system. The script will use environment
# variables if they are set, otherwise it will fall back to the values here.
#
# Example of setting an environment variable in bash:
# export DB_HOST="my.database.com"

password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
# Make sure your environment variable is set!
if not password:
    print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    exit(1)
session = MloxSession("mlox", password)
infra = session.infra

pdb = infra.get_service("feast-latest")
if not pdb:
    print("Could not load service")
    exit(1)

bundle = infra.get_bundle_by_service(pdb)
if not bundle:
    print("Could not load server")
    exit(1)

path = setup_feast_config(pdb)
store = FeatureStore(fs_yaml_file=Path(f"{path}/local_feature_store.yaml"))
teardown_feast_config(path)

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

print(store.list_on_demand_feature_views())

feature_service = store.get_feature_service("driver_activity_v3")
print(feature_service)
# online_response = store.get_online_features(
#     entity_rows=entity_rows,
#     # features=feature_service,
#     features=[
#         "driver_hourly_stats:conv_rate",
#         "driver_hourly_stats:acc_rate",
#     ],
# ).to_df()
# print(online_response)

training_df = store.get_historical_features(entity_df, features).to_df()

store.materialize_incremental(end_date=datetime.now())  # results in NotImplementedError
# store.materialize(
#     start_date=datetime.fromisoformat("2019-01-01"), end_date=datetime.now()
# )  # results in NotImplementedError

print("----- Feature schema -----\n")
training_df.info()

print()
print("-----  Features -----\n")
print(training_df.head())

print("------training_df----")

print(training_df)

# Cleanup temporary Feast config directory
try:
    teardown_feast_config(path)
except Exception:
    pass
