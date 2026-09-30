"""Continuously call the demonstrator endpoint with interactive fault injection."""

from __future__ import annotations

import argparse
import threading
import uuid

import requests
import urllib3

from examples.load_project_data import load_project_workspace
from examples.operations_demo.model import MODEL_NAME, demonstration_batch
from mlox.services.mlflow_gateway.base import MLFlowGatewayService


class TrafficLoop:
    def __init__(self, interval: float) -> None:
        workspace = load_project_workspace()
        gateways = [
            service
            for bundle in workspace.infrastructure.bundles
            for service in bundle.services
            if isinstance(service, MLFlowGatewayService)
            and service.state == "running"
        ]
        if not gateways:
            raise RuntimeError("No running MLflow Gateway service was found.")
        self.gateway = gateways[0]
        self.interval = interval
        self.corrupt = False
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._request_number = 0

    def set_corrupt(self, enabled: bool) -> None:
        with self._lock:
            self.corrupt = enabled
        print(f"Corruption is now {'ON' if enabled else 'OFF'}.")

    def run(self) -> None:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        batch = demonstration_batch()
        payload_frame = {
            "columns": list(batch.columns),
            "data": batch.values.tolist(),
        }
        while not self.stop_event.is_set():
            with self._lock:
                corrupt = self.corrupt
            payload = {
                "dataframe_split": payload_frame,
                "params": {"corrupt": corrupt},
                "registry_model_name": MODEL_NAME,
                "registry_model_alias": "champion",
            }
            self._request_number += 1
            try:
                response = requests.post(
                    f"{self.gateway.service_url.rstrip('/')}/prod/predict",
                    json=payload,
                    auth=(self.gateway.user, self.gateway.pw),
                    headers={
                        "X-MLOX-Pipeline-ID": uuid.uuid4().hex,
                        "X-MLOX-Pipeline-Name": "operations-demonstrator",
                    },
                    verify=False,
                    timeout=max(30.0, self.interval * 2),
                )
                response.raise_for_status()
                print(
                    f"request {self._request_number}: ok "
                    f"(corruption={'on' if corrupt else 'off'})"
                )
            except Exception as exc:
                print(f"request {self._request_number}: failed: {exc}")
            self.stop_event.wait(self.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between requests")
    args = parser.parse_args()
    loop = TrafficLoop(max(0.1, args.interval))
    worker = threading.Thread(target=loop.run, daemon=True)
    worker.start()
    print("Sending healthy traffic. Commands: on, off, status, quit")
    try:
        while True:
            command = input("operations-demo> ").strip().lower()
            if command in {"on", "corrupt on"}:
                loop.set_corrupt(True)
            elif command in {"off", "corrupt off"}:
                loop.set_corrupt(False)
            elif command == "status":
                print(f"Corruption is {'ON' if loop.corrupt else 'OFF'}.")
            elif command in {"quit", "q", "exit"}:
                break
            elif command:
                print("Commands: on, off, status, quit")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        loop.stop_event.set()
        worker.join(timeout=max(1.0, loop.interval + 1.0))
        print("Traffic stopped.")


if __name__ == "__main__":
    main()
