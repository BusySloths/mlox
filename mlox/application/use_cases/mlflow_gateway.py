from __future__ import annotations

import re
from typing import Any

import requests
import urllib3

from mlox.application.result import OperationResult


_SAMPLE_RE = re.compile(
    r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>.*)\})?\s+'
    r'(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)$'
)
_LABEL_RE = re.compile(r'(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>(?:\\.|[^"])*)"')


def describe_gateway(service, *, timeout: int = 10) -> OperationResult:
    """Load registry models, cache state, and Prometheus metrics for a gateway."""

    if service is None:
        return OperationResult(False, 30, "MLflow Gateway service is unavailable.")

    models, messages = _registry_models(service)
    cache: dict[str, Any] = {}
    metric_rows: list[dict[str, Any]] = []
    base_url = str(getattr(service, "service_url", "") or "").rstrip("/")
    if not base_url:
        messages.append("Gateway URL is unavailable.")
    else:
        cache_result = _gateway_get(service, f"{base_url}/cache", timeout=timeout)
        if cache_result.success:
            cache = cache_result.data or {}
        else:
            messages.append(cache_result.message)

        metrics_result = _gateway_get(
            service, f"{base_url}/metrics", timeout=timeout, as_text=True
        )
        if metrics_result.success:
            metric_rows = parse_prometheus_metrics(
                str((metrics_result.data or {}).get("text", ""))
            )
        else:
            messages.append(metrics_result.message)

    summary = _metric_summary(metric_rows, cache)
    return OperationResult(
        True,
        0,
        " ".join(messages) if messages else "MLflow Gateway settings loaded.",
        {
            "models": models,
            "cache": cache,
            "metrics": metric_rows,
            "summary": summary,
        },
    )


def clear_gateway_cache(service, *, timeout: int = 10) -> OperationResult:
    base_url = str(getattr(service, "service_url", "") or "").rstrip("/")
    if not base_url:
        return OperationResult(False, 31, "Gateway URL is unavailable.")
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.delete(
            f"{base_url}/cache",
            auth=_gateway_auth(service),
            verify=False,
            timeout=timeout,
        )
    except Exception as exc:
        return OperationResult(False, 32, f"Could not clear gateway cache: {exc}")
    if not response.ok:
        return OperationResult(
            False,
            response.status_code,
            f"Gateway returned HTTP {response.status_code}.",
        )
    payload = response.json()
    count = int(payload.get("cleared_models_count", 0))
    return OperationResult(True, 0, f"Cleared {count} cached model(s).", payload)


def parse_prometheus_metrics(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line.strip())
        if not match or not match.group("name").startswith("mlox_gateway_"):
            continue
        labels = {
            label.group("name"): bytes(label.group("value"), "utf-8")
            .decode("unicode_escape")
            for label in _LABEL_RE.finditer(match.group("labels") or "")
        }
        rows.append(
            {
                "name": match.group("name"),
                "labels": labels,
                "value": float(match.group("value")),
            }
        )
    return rows


def _gateway_get(service, url: str, *, timeout: int, as_text: bool = False):
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(
            url,
            auth=_gateway_auth(service),
            verify=False,
            timeout=timeout,
        )
    except Exception as exc:
        endpoint = url.rsplit("/", 1)[-1]
        return OperationResult(False, 33, f"Could not load {endpoint}: {exc}")
    if not response.ok:
        return OperationResult(
            False,
            response.status_code,
            f"{url.rsplit('/', 1)[-1].title()} returned HTTP {response.status_code}.",
        )
    data = {"text": response.text} if as_text else response.json()
    return OperationResult(True, 0, "Gateway endpoint loaded.", data)


def _gateway_auth(service) -> tuple[str, str]:
    return str(getattr(service, "user", "")), str(getattr(service, "pw", ""))


def _registry_models(service) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        registry = service.get_registry()
        if registry:
            return list(registry.list_models()), []
        return [], ["No registry linked."]
    except Exception as exc:
        return [], [f"Could not load registry models: {exc}"]


def _metric_summary(
    rows: list[dict[str, Any]], cache: dict[str, Any]
) -> dict[str, int | float]:
    def total(name: str, **labels: str) -> float:
        return sum(
            row["value"]
            for row in rows
            if row["name"] == name
            and all(row["labels"].get(key) == value for key, value in labels.items())
        )

    predictions = total("mlox_gateway_predictions_total")
    successful = total("mlox_gateway_predictions_total", status="success")
    return {
        "requests": total("mlox_gateway_http_requests_total"),
        "predictions": predictions,
        "prediction_errors": max(0.0, predictions - successful),
        "cache_hits": total("mlox_gateway_model_cache_operations_total", result="hit"),
        "cache_misses": total(
            "mlox_gateway_model_cache_operations_total", result="miss"
        ),
        "cached_models": len(cache.get("cached_models", []) or []),
    }
