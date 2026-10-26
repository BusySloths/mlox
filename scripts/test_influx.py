"""Read-only Core 3 token diagnostic; requires MLOX_PROJECT_PATH/PASSWORD."""
import argparse
import hmac
import json
import os
import shlex

import requests

from mlox.project import ProjectWorkspace
from mlox.execution.base import TaskGroup
from mlox.services.influx.client import InfluxClient


def query_status(connection, token):
    certificate = connection.get("certificate") or None
    if isinstance(certificate, str):
        certificate = certificate.encode()
    try:
        client = InfluxClient(
            url=connection["url"], token=token, database=connection["database"],
            certificate=certificate,
        )
        client.query("SELECT 1 AS authenticated", max_rows=1)
        return "OK"
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else "unknown"
        return f"HTTP {status}"
    except requests.exceptions.SSLError:
        return "TLS verification failed"
    except requests.RequestException:
        return "Connection failed"
    except (ValueError, KeyError):
        return "Invalid connection configuration"


def diagnose(bundle, service):
    connection = service.get_secrets()["influx_connection"]
    token = connection["token"]
    lines = [f"Workspace token query: {query_status(connection, token)}"]
    try:
        with bundle.server.get_server_connection() as conn:
            inspect = service.exec.execute(
                conn,
                "sudo docker inspect --format "
                "'{{json .Config.Labels}}|{{json .Mounts}}|{{json .Config.Cmd}}' "
                "influxdb3",
                group=TaskGroup.SECURITY_ASSETS, sudo=True,
                description="Inspect Influx container mounts for authentication diagnosis",
            )
        labels_raw, mounts_raw, command_raw = inspect.split("|", maxsplit=2)
        labels = json.loads(labels_raw)
        mounts = json.loads(mounts_raw)
        command = json.loads(command_raw)
        lines.append(
            "Container Compose project: "
            f"{labels.get('com.docker.compose.project', 'unknown')}"
        )
        lines.append(
            "Container Compose directory: "
            f"{labels.get('com.docker.compose.project.working_dir', 'unknown')}"
        )
        lines.append("Container mount points: " + ", ".join(
            f"{mount.get('Destination')} <- {mount.get('Source')}"
            for mount in mounts
        ))
        secret_mount = next(
            (mount for mount in mounts
             if mount.get("Destination") == "/run/secrets/influxdb3-admin-token"),
            None,
        )
        if secret_mount is None:
            lines.append("Container has no Influx admin-token secret mount.")
            lines.append(
                "Container command references admin-token-file: "
                f"{'yes' if any('admin-token-file' in arg for arg in command) else 'no'}"
            )
            return lines
        source = secret_mount.get("Source")
        if not source:
            lines.append("Influx token secret mount has no host source path.")
            return lines
        with bundle.server.get_server_connection() as conn:
            content = service.exec.execute(
                conn, f"sudo cat -- {shlex.quote(source)}",
                group=TaskGroup.SECURITY_ASSETS, sudo=True,
                description="Read mounted Influx token for authentication diagnosis",
            )
        if not content:
            raise ValueError("Could not read the mounted Influx token source")
        bootstrap_token = json.loads(content)["token"]
        matches = hmac.compare_digest(token.encode(), bootstrap_token.encode())
    except Exception:
        lines.append("Could not inspect the running Influx container or token mount.")
        return lines
    lines.append(f"Workspace and deployed bootstrap tokens match: {'yes' if matches else 'NO'}")
    lines.append(f"Bootstrap token query: {query_status(connection, bootstrap_token)}")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-uuid")
    args = parser.parse_args()
    path = os.environ.get("MLOX_PROJECT_PATH")
    password = os.environ.get("MLOX_PROJECT_PASSWORD")
    if not path or not password:
        parser.error("Set MLOX_PROJECT_PATH and MLOX_PROJECT_PASSWORD.")
    workspace = ProjectWorkspace.open(path, password)
    candidates = [
        (bundle, service)
        for bundle in workspace.infrastructure.bundles
        for service in bundle.services
        if callable(getattr(service, "get_influx_env_binding", None))
        and (not args.service_uuid or str(service.uuid) == args.service_uuid)
    ]
    if len(candidates) != 1:
        parser.error("Expected one InfluxDB service; use --service-uuid to select it.")
    for line in diagnose(*candidates[0]):
        print(line)


if __name__ == "__main__":
    main()
