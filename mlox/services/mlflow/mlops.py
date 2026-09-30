import os
import logging
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import numpy as np
import pandas as pd  # type: ignore

from typing import Any, List, Dict, Sequence, Iterator
from abc import ABC, abstractmethod

import mlflow  # type: ignore
from mlflow.models.model import ModelInfo  # type: ignore
from mlflow.tracking import MlflowClient  # type: ignore

from mlox.secret_manager import (
    SECRET_MANAGER_KEYFILE_ENV,
    SECRET_MANAGER_KEYFILE_PW_ENV,
    AbstractSecretManager,
    load_secret_manager_from_env,
)
from mlox.services.otel.client import (
    OTelClient,
    get_telemetry_client as get_process_telemetry_client,
)

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


logger = logging.getLogger(__name__)

PIPELINE_ID_HEADER = "X-MLOX-Pipeline-ID"
PIPELINE_NAME_HEADER = "X-MLOX-Pipeline-Name"
_MODEL_STEP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class ModelInvocationContext:
    """Request-local identity of one concrete registered-model invocation."""

    pipeline_id: str
    pipeline_name: str
    request_id: str
    model_name: str
    model_version: str
    model_alias: str | None = None

    def telemetry_attributes(self) -> Dict[str, str]:
        attributes = {
            "mlox.pipeline.id": self.pipeline_id,
            "mlox.pipeline.name": self.pipeline_name,
            "mlox.model.name": self.model_name,
            "mlox.model.version": self.model_version,
        }
        if self.request_id:
            attributes["mlox.request.id"] = self.request_id
        if self.model_alias:
            attributes["mlox.model.alias"] = self.model_alias
        return attributes


_MODEL_INVOCATION: ContextVar[ModelInvocationContext | None] = ContextVar(
    "mlox_model_invocation",
    default=None,
)
_MODEL_STEP_PATH: ContextVar[tuple[str, ...]] = ContextVar(
    "mlox_model_step_path",
    default=(),
)


@contextmanager
def model_invocation_context(
    invocation: ModelInvocationContext,
) -> Iterator[ModelInvocationContext]:
    """Expose an invocation to a loaded model for the duration of prediction."""

    invocation_token = _MODEL_INVOCATION.set(invocation)
    path_token = _MODEL_STEP_PATH.set(())
    try:
        yield invocation
    finally:
        _MODEL_STEP_PATH.reset(path_token)
        _MODEL_INVOCATION.reset(invocation_token)


def current_model_invocation() -> ModelInvocationContext | None:
    return _MODEL_INVOCATION.get()


@dataclass
class ModelStep:
    """Handle used to add safe observations to the active model-step span."""

    name: str
    qualified_name: str
    span: Any = None

    def set_attribute(self, name: str, value: Any) -> None:
        if self.span is not None and value is not None:
            self.span.set_attribute(name, value)

    def observe_array(
        self,
        name: str,
        values: np.ndarray | pd.DataFrame | pd.Series | Sequence[Any],
    ) -> None:
        """Record bounded statistical summaries without exporting raw values."""

        if self.span is None:
            return
        observation_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("_")
        if not observation_name:
            raise ValueError("Observation name must contain a valid character.")
        prefix = f"mlox.observation.{observation_name}"
        array = (
            values.to_numpy()
            if isinstance(values, (pd.DataFrame, pd.Series))
            else np.asarray(values)
        )
        self.set_attribute(f"{prefix}.dimensions", list(array.shape))
        self.set_attribute(f"{prefix}.size", int(array.size))
        if array.size == 0:
            return
        try:
            numeric = np.asarray(array, dtype=float)
        except (TypeError, ValueError):
            return
        finite = numeric[np.isfinite(numeric)]
        self.set_attribute(
            f"{prefix}.missing_fraction",
            float(1.0 - (finite.size / numeric.size)),
        )
        if finite.size == 0:
            return
        self.set_attribute(f"{prefix}.mean", float(np.mean(finite)))
        self.set_attribute(f"{prefix}.std", float(np.std(finite)))
        self.set_attribute(f"{prefix}.min", float(np.min(finite)))
        self.set_attribute(f"{prefix}.max", float(np.max(finite)))

    def observe_value(self, name: str, value: float | int) -> None:
        """Record one scalar observation on the active model-step span."""

        observation_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("_")
        if not observation_name:
            raise ValueError("Observation name must contain a valid character.")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Scalar observations must be numeric.") from exc
        self.set_attribute(
            f"mlox.observation.{observation_name}.value", numeric_value
        )


@contextmanager
def _optional_telemetry_span(
    telemetry: OTelClient | None,
    name: str,
    attributes: Dict[str, Any],
    *,
    kind: str = "internal",
) -> Iterator[Any]:
    if telemetry is None:
        yield None
        return
    with telemetry.span(name, attributes, kind=kind) as span:
        yield span


_EXCLUDED_CODE_PATH_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "venv",
    }
)


class DeployableModel(ABC):
    def get_secret_manager(self) -> AbstractSecretManager | None:
        """Load the secret manager exposed to the serving process, if configured."""

        if not (
            os.environ.get(SECRET_MANAGER_KEYFILE_ENV)
            and os.environ.get(SECRET_MANAGER_KEYFILE_PW_ENV)
        ):
            return None
        return load_secret_manager_from_env()

    def get_telemetry_client(self) -> OTelClient | None:
        """Return the gateway's process-wide telemetry client, if configured."""

        return get_process_telemetry_client()

    def get_runtime_context(self) -> ModelInvocationContext | None:
        return current_model_invocation()

    def get_outbound_headers(self) -> Dict[str, str]:
        """Return headers that continue the active trace and pipeline identity."""

        headers: Dict[str, str] = {}
        runtime = self.get_runtime_context()
        if runtime is not None:
            headers[PIPELINE_ID_HEADER] = runtime.pipeline_id
            headers[PIPELINE_NAME_HEADER] = runtime.pipeline_name
        telemetry = self.get_telemetry_client()
        if telemetry is not None:
            telemetry.inject_context(headers)
        return headers

    @contextmanager
    def model_step(
        self,
        name: str,
        *,
        component: str | None = None,
        component_version: str | int | None = None,
        kind: str | None = None,
    ) -> Iterator[ModelStep]:
        """Create a hierarchical, observable step below ``live_predict``."""

        name = str(name).strip()
        if not _MODEL_STEP_NAME_PATTERN.fullmatch(name):
            raise ValueError(
                "Model step names must start with an alphanumeric character and "
                "contain only letters, numbers, dots, underscores, or hyphens."
            )
        current_path = _MODEL_STEP_PATH.get()
        path = (*current_path, name)
        runtime = self.get_runtime_context()
        model_name = (
            runtime.model_name if runtime is not None else self.__class__.__name__
        )
        qualified_name = "/".join((model_name, *path))
        attributes: Dict[str, Any] = {
            "mlox.step.name": name,
            "mlox.step.path": qualified_name,
            "mlox.step.depth": len(path),
        }
        if runtime is not None:
            attributes.update(runtime.telemetry_attributes())
        if component:
            attributes["mlox.component.name"] = str(component)
        if component_version is not None:
            attributes["mlox.component.version"] = str(component_version)
        if kind:
            attributes["mlox.step.kind"] = str(kind)

        token = _MODEL_STEP_PATH.set(path)
        telemetry = self.get_telemetry_client()
        try:
            with _optional_telemetry_span(
                telemetry,
                "mlox.model.step",
                attributes,
            ) as span:
                yield ModelStep(name=name, qualified_name=qualified_name, span=span)
        finally:
            _MODEL_STEP_PATH.reset(token)

    @abstractmethod
    def live_predict(
        self,
        input: np.ndarray | pd.DataFrame,
        params: Dict | None = None,
        artifacts: Dict | None = None,
    ) -> pd.DataFrame:
        pass

    @abstractmethod
    def tracked_training(self, params: Dict | None = None) -> Dict | None:
        pass


class MLFlowDeployableModelService(mlflow.pyfunc.PythonModel):  # type: ignore
    registered_model_name: str | None
    registered_model_version: int | None
    requirements_file: str | None
    requirements_python_version: str | None
    run_id: str | None
    logged_model_info: ModelInfo | None

    def __init__(
        self,
        model: DeployableModel,
        model_class: str,
        code_paths: Sequence[str] | None = None,
        requirements_file: str | None = None,
        requirements_python_version: str = "3.12.5",
    ) -> None:
        self.model = model
        self.model_class = model_class
        self.artifacts = None
        self.model_config = None
        self.tracking_uri = os.environ["MLFLOW_URI"]
        self.registry_uri = os.environ["MLFLOW_URI"]
        self.code_paths = list(code_paths) if code_paths is not None else []
        self.registered_model_name = None
        self.registered_model_version = None
        self.requirements_file = requirements_file
        self.requirements_python_version = requirements_python_version
        self.run_id = None
        self.logged_model_info = None

    def set_registered_model_name(self, registered_model_name: str | None) -> None:
        if registered_model_name:
            logger.info("Setting registered model name to '%s'", registered_model_name)
        else:
            logger.info(
                "Clearing registered model name means that model won't be registered."
            )
        self.registered_model_name = registered_model_name

    def set_alias(self, alias: str) -> None:
        """Set the single registry alias to apply to the logged model version."""
        if not self.registered_model_name or self.registered_model_version is None:
            logger.info(
                "Deferring alias '%s' because no registered model version is available.",
                alias,
            )
            return
        logger.info(
            "Setting alias '%s' for registered model '%s' version %s.",
            alias,
            self.registered_model_name,
            self.registered_model_version,
        )
        client = MlflowClient()
        client.set_registered_model_alias(
            name=self.registered_model_name,
            alias=alias,
            version=str(self.registered_model_version),
        )

    def track_model(
        self,
        params: Dict | None = None,
        input_example: np.ndarray | pd.DataFrame | None = None,
        inference_params: Dict | None = None,
    ) -> ModelInfo:
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_registry_uri(self.registry_uri)
        mlflow.set_experiment(f"{self.model_class}")

        run_tags = {"model": self.model_class}
        with mlflow.start_run(log_system_metrics=True, tags=run_tags):
            with mlflow.start_span("tracked-training") as span:
                span.set_inputs({"params": params})
                artifacts = self.model.tracked_training(params=params)
                span.set_attribute("attrib1", "value1")
                span.set_outputs({"artifacts": artifacts})

            signature: mlflow.models.ModelSignature | None = None
            if input_example is not None:
                with mlflow.start_span("infer-signature") as span:
                    logger.info(
                        "Inferring signature for the model input with type %s",
                        type(input_example),
                    )
                    signature = mlflow.models.infer_signature(
                        input_example,
                        self.model.live_predict(
                            input_example, params=params, artifacts=artifacts
                        ),
                        params=inference_params,
                    )
                    logger.info("Signature inferred successfully: %s", signature)
            else:
                logger.info("No input example provided; skipping signature inference.")

            if artifacts is None:
                artifacts = dict()

            mlflow.set_tag("python_class", str(self.model.__class__))

            with self._prepared_code_paths_for_logging() as prepared_code_paths:
                model_info = mlflow.pyfunc.log_model(
                    name=self.model_class,
                    python_model=self,
                    code_paths=prepared_code_paths or None,
                    conda_env=self.get_conda_env(),
                    signature=signature,
                    input_example=input_example,
                    registered_model_name=self.registered_model_name,
                    artifacts=artifacts,
                )
            self._store_logged_model_info(model_info)
            return model_info

    def get_conda_env(self) -> Dict:
        """Create a conda environment for the MLflow model."""
        if self.requirements_file is None:
            return {
                "name": "mlflow-models",
                "channels": ["defaults"],
                "dependencies": [
                    f"python={self.requirements_python_version or '3.12.5'}",
                    {"pip": [f"mlflow=={mlflow.__version__}"]},
                ],
            }
        return {
            "name": "mlflow-models",
            "channels": ["defaults"],
            "dependencies": [
                f"python={self.requirements_python_version or '3.12.5'}",
                {"pip": [f"-r {self.requirements_file}"]},
            ],
        }

    def load_context(self, context):
        """This method is called when loading an MLflow model with pyfunc.load_model(),
            as soon as the Python Model is constructed.
        Args:
            context: MLflow context where the model artifact is stored.
        """
        logger.info(f"Load context called with context={context}")
        # self._add_code_paths_to_pythonpath(context)
        self.artifacts = context.artifacts or {}
        logger.info(f"Load artifacts {list(self.artifacts.keys())}")
        self.model_config = context.model_config
        if self.model_config is not None:
            logger.info(f"Load model_config {list(self.model_config.keys())}")

        logger.info("Done.")

    def predict(self, context, model_input, params=None) -> pd.DataFrame:
        if params is None:
            params = {}
        telemetry = self.model.get_telemetry_client()
        runtime = self.model.get_runtime_context()
        if runtime is None:
            trace_id = telemetry.current_trace_id() if telemetry is not None else ""
            runtime = ModelInvocationContext(
                pipeline_id=trace_id or uuid.uuid4().hex,
                pipeline_name=self.model_class,
                request_id="",
                model_name=self.registered_model_name or self.model_class,
                model_version=str(self.registered_model_version or "unknown"),
            )
        attributes: Dict[str, Any] = runtime.telemetry_attributes()
        attributes["mlox.model.class"] = self.model_class
        attributes["mlox.input.type"] = type(model_input).__name__
        try:
            attributes["mlox.input.rows"] = len(model_input)
        except TypeError:
            pass

        started = time.perf_counter()
        status = "success"
        with model_invocation_context(runtime):
            with _optional_telemetry_span(
                telemetry,
                "mlox.model.live_predict",
                attributes,
            ) as span:
                try:
                    result = self.model.live_predict(
                        model_input,
                        params=params,
                        artifacts=self.artifacts,
                    )
                    if span is not None:
                        try:
                            span.set_attribute("mlox.output.rows", len(result))
                        except TypeError:
                            pass
                except Exception as exc:
                    status = "error"
                    if span is not None:
                        span.record_exception(exc)
                        if telemetry is not None:
                            telemetry.mark_span_error(span)
                    logger.exception(
                        "Model prediction failed for %s.", runtime.model_name
                    )
                    result = pd.DataFrame({"error": [str(exc)]})
                finally:
                    duration = time.perf_counter() - started
                    metric_attributes = {
                        "mlox.model.name": runtime.model_name,
                        "mlox.model.version": runtime.model_version,
                        "mlox.prediction.status": status,
                    }
                    if telemetry is not None:
                        try:
                            telemetry.send_metric(
                                "mlox.model.predictions",
                                1,
                                metric_attributes,
                            )
                            telemetry.send_histogram(
                                "mlox.model.prediction.duration",
                                duration,
                                metric_attributes,
                                unit="s",
                                description="Model live prediction duration",
                            )
                            telemetry.send_log(
                                "Model prediction completed.",
                                severity="ERROR" if status == "error" else "INFO",
                                attributes=metric_attributes,
                            )
                        except Exception:
                            logger.warning(
                                "Could not export model prediction metrics.",
                                exc_info=True,
                            )
        logger.info(
            "Model prediction completed for %s version %s.",
            runtime.model_name,
            runtime.model_version,
        )
        return result

    def _resolve_code_paths_for_logging(self) -> List[str]:
        resolved_paths: List[str] = []
        base_dir = Path.cwd()
        for path_str in self.code_paths:
            path = Path(path_str).expanduser()
            if not path.is_absolute():
                path = (base_dir / path).resolve()
            if path.exists():
                resolved_paths.append(str(path))
            else:
                logger.warning(
                    "Configured code path '%s' does not exist (resolved to %s); "
                    "it will be skipped during logging.",
                    path_str,
                    path,
                )
        if not resolved_paths:
            logger.info("No valid code paths configured for MLflow model logging.")
        return resolved_paths

    def _ignore_code_path_entries(
        self,
        _directory: str,
        names: list[str],
    ) -> set[str]:
        return {name for name in names if name in _EXCLUDED_CODE_PATH_NAMES}

    @contextmanager
    def _prepared_code_paths_for_logging(self) -> Iterator[List[str]]:
        prepared_paths: List[str] = []
        temp_dirs: list[tempfile.TemporaryDirectory[str]] = []
        try:
            for path_str in self._resolve_code_paths_for_logging():
                path = Path(path_str)
                if path.is_dir():
                    temp_dir = tempfile.TemporaryDirectory(
                        prefix="mlox-mlflow-code-path-"
                    )
                    temp_dirs.append(temp_dir)
                    staged_path = Path(temp_dir.name) / path.name
                    shutil.copytree(
                        path,
                        staged_path,
                        ignore=self._ignore_code_path_entries,
                    )
                    prepared_paths.append(str(staged_path))
                else:
                    prepared_paths.append(str(path))
            yield prepared_paths
        finally:
            for temp_dir in reversed(temp_dirs):
                temp_dir.cleanup()

    def _store_logged_model_info(self, model_info: ModelInfo) -> None:
        self.logged_model_info = model_info
        self.run_id = model_info.run_id
        self.registered_model_version = model_info.registered_model_version
        logger.info(
            "Logged MLflow model '%s' with run_id=%s, model_uri=%s, "
            "registered_model_version=%s",
            self.model_class,
            self.run_id,
            model_info.model_uri,
            self.registered_model_version,
        )


def list_versions_for_model(model_name: str) -> List:
    mlflow.set_tracking_uri(os.environ["MLFLOW_URI"])
    mlflow.set_registry_uri(os.environ["MLFLOW_URI"])

    names = list()
    client = MlflowClient()
    filter_string = f"name='{model_name}'"
    for rm in client.search_model_versions(filter_string):
        names.append(rm)
    return names


if __name__ == "__main__":
    logger.info(list_versions_for_model(model_name="Test"))
