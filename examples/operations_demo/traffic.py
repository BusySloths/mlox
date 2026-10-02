"""Continuously call the demonstrator endpoint with interactive fault injection."""

from __future__ import annotations

import argparse
import threading
import uuid

import numpy as np
import requests
import urllib3

from examples.load_project_data import load_project_workspace
from examples.operations_demo.model import MODEL_NAME, demonstration_batch
from mlox.services.mlflow_gateway.base import MLFlowGatewayService


class TrafficLoop:
    def __init__(
        self,
        interval: float,
        gateway_uuid: str | None = None,
        *,
        feature_noise: float = 0.03,
        label_noise: float = 0.02,
        seed: int = 2026,
    ) -> None:
        self.workspace = load_project_workspace()
        self.gateways = [
            service
            for bundle in self.workspace.infrastructure.bundles
            for service in bundle.services
            if isinstance(service, MLFlowGatewayService)
        ]
        running = [gateway for gateway in self.gateways if gateway.state == "running"]
        if not running:
            raise RuntimeError("No running MLflow Gateway service was found.")
        self.gateway = running[0]
        self.interval = interval
        self.corrupt = False
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._request_number = 0
        self.feature_noise = max(0.0, feature_noise)
        self.label_noise = max(0.0, label_noise)
        self._rng = np.random.default_rng(seed)
        if gateway_uuid:
            self.select_gateway(gateway_uuid)

    def select_gateway(self, gateway_uuid: str) -> None:
        """Select a running gateway by its full UUID or an unambiguous prefix."""

        selector = gateway_uuid.strip()
        matches = [
            gateway
            for gateway in self.gateways
            if gateway.uuid == selector or gateway.uuid.startswith(selector)
        ]
        if not matches:
            raise ValueError(f"No MLflow Gateway matches UUID {selector!r}.")
        if len(matches) > 1:
            raise ValueError(f"Gateway UUID prefix {selector!r} is ambiguous.")
        gateway = matches[0]
        if gateway.state != "running":
            raise ValueError(
                f"MLflow Gateway {gateway.uuid} is {gateway.state}, not running."
            )
        with self._lock:
            self.gateway = gateway
        print(
            f"Using MLflow Gateway {gateway.name} ({gateway.uuid}) at "
            f"{gateway.service_url.rstrip('/')}"
        )

    @staticmethod
    def _service_endpoints(service) -> list[str]:
        candidates = [
            getattr(service, "service_url", ""),
            getattr(service, "tracking_uri", ""),
            getattr(service, "collector_url", ""),
            *(getattr(service, "service_urls", {}) or {}).values(),
        ]
        return list(dict.fromkeys(str(value) for value in candidates if value))

    @classmethod
    def _service_summary(cls, label: str, service, service_uuid: str | None) -> str:
        if not service_uuid:
            return f"  {label}: not bound"
        if service is None:
            return f"  {label}: unavailable ({service_uuid})"
        endpoints = cls._service_endpoints(service)
        endpoint_text = ", ".join(endpoints) if endpoints else "no endpoint"
        return (
            f"  {label}: {service.name} ({service.uuid}), "
            f"state={service.state}, endpoint={endpoint_text}"
        )

    def gateway_lines(self) -> list[str]:
        with self._lock:
            selected_uuid = self.gateway.uuid
        lines = ["Configured MLflow Gateways:"]
        for gateway in self.gateways:
            marker = "*" if gateway.uuid == selected_uuid else " "
            lines.append(
                f" {marker} {gateway.name} ({gateway.uuid}), state={gateway.state}, "
                f"endpoint={gateway.service_url.rstrip('/')}"
            )
        return lines

    def status_lines(self) -> list[str]:
        with self._lock:
            gateway = self.gateway
            corrupt = self.corrupt
        lines = [
            f"Corruption is {'ON' if corrupt else 'OFF'}.",
            (
                f"Noise: feature σ={self.feature_noise:g}, "
                f"label σ={self.label_noise:g}."
            ),
            "Connected services:",
            self._service_summary("Gateway", gateway, gateway.uuid),
        ]
        dependencies = (
            ("Registry", "registry_uuid"),
            ("Telemetry", "telemetry_uuid"),
            ("Secret manager", "secret_manager_uuid"),
            ("TLS secret manager", "tls_secret_manager_uuid"),
        )
        for label, field_name in dependencies:
            service_uuid = getattr(gateway, field_name, None)
            service = (
                gateway.get_dependent_service(service_uuid) if service_uuid else None
            )
            lines.append(self._service_summary(label, service, service_uuid))
        return lines

    def set_corrupt(self, enabled: bool) -> None:
        with self._lock:
            self.corrupt = enabled
        print(f"Corruption is now {'ON' if enabled else 'OFF'}.")

    def run(self) -> None:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        while not self.stop_event.is_set():
            with self._lock:
                corrupt = self.corrupt
                gateway = self.gateway
            batch = demonstration_batch(
                rng=self._rng,
                feature_noise=self.feature_noise,
                label_noise=self.label_noise,
            )
            payload_frame = {
                "columns": list(batch.columns),
                "data": batch.values.tolist(),
            }
            payload = {
                "dataframe_split": payload_frame,
                "params": {"corrupt": corrupt},
                "registry_model_name": MODEL_NAME,
                "registry_model_alias": "champion",
            }
            self._request_number += 1
            try:
                response = requests.post(
                    f"{gateway.service_url.rstrip('/')}/prod/predict",
                    json=payload,
                    auth=(gateway.user, gateway.pw),
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
    parser.add_argument(
        "--gateway",
        metavar="UUID",
        help="Select a running MLflow Gateway by UUID or an unambiguous UUID prefix",
    )
    parser.add_argument(
        "--feature-noise",
        type=float,
        default=0.03,
        help="Gaussian feature noise standard deviation",
    )
    parser.add_argument(
        "--label-noise",
        type=float,
        default=0.02,
        help="Gaussian label noise standard deviation",
    )
    parser.add_argument("--seed", type=int, default=2026, help="Traffic random seed")
    args = parser.parse_args()
    loop = TrafficLoop(
        max(0.1, args.interval),
        gateway_uuid=args.gateway,
        feature_noise=args.feature_noise,
        label_noise=args.label_noise,
        seed=args.seed,
    )
    worker = threading.Thread(target=loop.run, daemon=True)
    worker.start()
    print("Sending healthy traffic. Commands: on, off, status, gateways, use <uuid>, quit")
    for line in loop.status_lines():
        print(line)
    try:
        while True:
            command = input("operations-demo> ").strip()
            normalized = command.lower()
            if normalized in {"on", "corrupt on"}:
                loop.set_corrupt(True)
            elif normalized in {"off", "corrupt off"}:
                loop.set_corrupt(False)
            elif normalized == "status":
                for line in loop.status_lines():
                    print(line)
            elif normalized == "gateways":
                for line in loop.gateway_lines():
                    print(line)
            elif normalized.startswith("use "):
                try:
                    loop.select_gateway(command.split(maxsplit=1)[1])
                except ValueError as exc:
                    print(exc)
            elif normalized in {"quit", "q", "exit"}:
                break
            elif command:
                print("Commands: on, off, status, gateways, use <uuid>, quit")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        loop.stop_event.set()
        worker.join(timeout=max(1.0, loop.interval + 1.0))
        print("Traffic stopped.")


if __name__ == "__main__":
    main()
