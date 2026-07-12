"""Docker deployment adapter for Apache Airflow service instances.

Purpose:
- Configure and manage Airflow containers, TLS assets, and runtime credentials on a target server.

Key public classes/functions:
- ``AirflowDockerService``

Expected runtime mode:
- Remote executor (invoked from CLI/UI/TUI orchestration)

Related modules (plain-text links):
- mlox.service
- mlox.executors
- mlox.services.airflow.ui
"""

import ssl
import json
import base64
import logging
import urllib.error
import urllib.parse
import urllib.request

from typing import Any, Dict
from dataclasses import dataclass, field

from mlox.secret_manager import (
    SECRET_MANAGER_KEYFILE_ENV,
    SECRET_MANAGER_KEYFILE_PW_ENV,
)
from mlox.service import (
    AbstractService,
    AbstractWebUIService,
    AbstractWorkflowOrchestratorService,
    ServiceCapability,
)
from mlox.utils import generate_password


logger = logging.getLogger(__name__)


@dataclass
class AirflowDockerService(
    AbstractService,
    AbstractWebUIService,
    AbstractWorkflowOrchestratorService,
):
    capabilities = {ServiceCapability.WORKFLOW_ORCHESTRATOR, ServiceCapability.WEB_UI}
    web_ui_url_label = "Airflow UI"
    web_ui_login_fields = ("username", "password")
    path_dags: str
    path_output: str
    ui_user: str
    ui_pw: str
    port: str
    secret_path: str = ""
    secret_key: str = field(
        default="9d54873d8b53466dbcfd00a2bb9a104caa8071143f864aa88c36d3f5a8c8615f",
        init=False,
    )
    workflow_secret_manager_uuid: str | None = field(default=None, init=False)
    workflow_secret_manager_env: Dict[str, str] = field(default_factory=dict, init=False)
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {
            "Airflow Webserver": "airflow-webserver",
            "Airflow Scheduler": "airflow-scheduler",
            "Airflow Worker": "airflow-worker",
            "Airflow Triggerer": "airflow-triggerer",
            "Airflow DAG Processor": "airflow-dag-processor",
            "Airflow Initializer": "airflow-init",
            "Airflow CLI": "airflow-cli",
            "Postgres": "postgres",
            "Redis": "redis",
        },
    )

    def __str__(self):
        return f"AirflowDockerService(path_dags={self.path_dags}, path_output={self.path_output}, ui_user={self.ui_user}, ui_pw={self.ui_pw}, port={self.port}, secret_path={self.secret_path})"

    def setup(self, conn) -> None:
        # copy files to target
        self.exec.fs_create_dir(conn, self.target_path)
        # Ensure host directories for DAGs and logs/outputs exist and are owned by mlox_user
        # This is crucial for volume mounts to have correct permissions for AIRFLOW_UID.
        self.exec.fs_create_dir(conn, self.path_dags)
        self.exec.fs_create_dir(conn, self.path_output)
        # self.exec.fs_create_dir(conn, self.target_path + "/logs")
        # self.exec.fs_create_dir(conn, self.target_path + "/plugins")

        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        self.exec.tls_setup(conn, conn.host, self.target_path)
        # setup environment
        base_url = f"https://{conn.host}:{self.port}"
        if len(self.secret_path) >= 1:
            base_url = f"https://{conn.host}:{self.port}/{self.secret_path}"
        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(conn, env_path, "_AIRFLOW_SSL_CERT_NAME=cert.pem")
        self.exec.fs_append_line(conn, env_path, "_AIRFLOW_SSL_KEY_NAME=key.pem")
        self.exec.fs_append_line(
            conn, env_path, f"AIRFLOW_UID={self.exec.sys_user_id(conn)}"
        )
        self.secret_key = generate_password(length=48)
        self.exec.fs_append_line(conn, env_path, f"_AIRFLOW_SECRET={self.secret_key}")
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_SSL_FILE_PATH={self.target_path}/"
        )
        self.exec.fs_append_line(conn, env_path, f"_AIRFLOW_OUT_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"_AIRFLOW_BASE_URL={base_url}")
        self.exec.fs_append_line(conn, env_path, f"_AIRFLOW_LOG_HOST={base_url}")
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_WWW_USER_USERNAME={self.ui_user}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_WWW_USER_PASSWORD={self.ui_pw}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_OUT_FILE_PATH={self.path_output}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"_AIRFLOW_DAGS_FILE_PATH={self.path_dags}"
        )
        self.exec.fs_append_line(conn, env_path, "_AIRFLOW_LOAD_EXAMPLES=false")
        self._write_workflow_secret_manager_env(conn, env_path)
        self.service_urls["Airflow UI"] = base_url
        self.service_ports["Airflow Webserver"] = int(self.port)

    def teardown(self, conn):
        self.exec.docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        self.exec.fs_delete_dir(conn, self.target_path)

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn, remove_volumes=True)

    def check(self, conn) -> Dict:
        """
        Checks if the Airflow API is responsive using the /api/v2/version endpoint.
        This corresponds to the health check from the docker-compose file:
        `curl --fail "${_AIRFLOW_BASE_URL:-http://localhost:8080}/api/v2/version"`
        """
        url = self.service_urls["Airflow UI"] + "/api/v2/version"
        logger.info(f"Performing health check on Airflow service at {url}")

        try:
            # Create an SSL context that does not verify certificates. This is
            # necessary for self-signed certificates used in local/dev setups.
            ssl_context = ssl._create_unverified_context()
            request = urllib.request.Request(url)
            # Airflow's REST API uses Basic Authentication.
            auth_string = f"{self.ui_user}:{self.ui_pw}"
            encoded_auth = base64.b64encode(auth_string.encode("utf-8")).decode("ascii")
            request.add_header("Authorization", f"Basic {encoded_auth}")

            with urllib.request.urlopen(
                request, timeout=10, context=ssl_context
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
                if "version" in data:
                    logger.info(f"Airflow health check OK. Version: {data['version']}")
                    return {"status": "running", "version": data["version"]}
                logger.warning(
                    "Health check failed: 'version' key not in response JSON."
                )
                return {
                    "status": "unknown",
                    "message": "'version' key missing in response",
                }
        except urllib.error.URLError as e:
            reason = (
                f"HTTP Status: {e.code}"
                if hasattr(e, "code")
                else f"Reason: {e.reason}"
            )
            logger.error(f"Airflow health check failed for {url}. {reason}")
            return {"status": "unknown", "message": f"Connection error: {reason}"}
        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                f"An unexpected error occurred during Airflow health check for {url}: {e}"
            )
            return {"status": "unknown", "message": f"Error: {e}"}

    def list_workflows(self) -> list[dict[str, Any]]:
        """Return Airflow DAG metadata with the latest DAG run when available."""

        dags_payload = self._airflow_api_get(
            "/dags",
            {
                "limit": "100",
            },
        )
        raw_dags = dags_payload.get("dags", [])
        if not isinstance(raw_dags, list):
            raise ValueError("Airflow DAG response did not contain a DAG list.")

        workflows: list[dict[str, Any]] = []
        for dag in raw_dags:
            if not isinstance(dag, dict):
                continue
            dag_id = str(dag.get("dag_id") or dag.get("dag_display_name") or "")
            if not dag_id:
                continue
            latest_run = self._latest_dag_run(dag_id)
            workflows.append(
                {
                    "id": dag_id,
                    "name": dag_id,
                    "schedule": self._dag_schedule(dag),
                    "is_paused": dag.get("is_paused"),
                    "is_active": dag.get("is_active"),
                    "owners": self._join_list(dag.get("owners")),
                    "tags": self._dag_tags(dag.get("tags")),
                    "fileloc": str(dag.get("fileloc") or ""),
                    "last_run_id": str(latest_run.get("dag_run_id") or ""),
                    "last_run_state": str(latest_run.get("state") or ""),
                    "last_run_start": str(
                        latest_run.get("start_date")
                        or latest_run.get("logical_date")
                        or latest_run.get("execution_date")
                        or ""
                    ),
                    "last_run_end": str(latest_run.get("end_date") or ""),
                }
            )
        return workflows

    def set_workflow_secret_manager_env(
        self,
        conn,
        *,
        manager_uuid: str,
        encrypted_keyfile: str,
        keyfile_password: str,
    ) -> None:
        """Expose a secret-manager keyfile to DAGs through Airflow env vars."""

        self.workflow_secret_manager_uuid = manager_uuid
        self.workflow_secret_manager_env = {
            SECRET_MANAGER_KEYFILE_ENV: encrypted_keyfile,
            SECRET_MANAGER_KEYFILE_PW_ENV: keyfile_password,
        }
        env_path = f"{self.target_path}/{self.target_docker_env}"
        self._write_workflow_secret_manager_env(conn, env_path)
        self.compose_up(conn)

    def _write_workflow_secret_manager_env(self, conn, env_path: str) -> None:
        if not self.workflow_secret_manager_env:
            return
        managed = {
            f"_{SECRET_MANAGER_KEYFILE_ENV}": self.workflow_secret_manager_env.get(
                SECRET_MANAGER_KEYFILE_ENV,
                "",
            ),
            f"_{SECRET_MANAGER_KEYFILE_PW_ENV}": self.workflow_secret_manager_env.get(
                SECRET_MANAGER_KEYFILE_PW_ENV,
                "",
            ),
        }
        existing = ""
        try:
            existing = str(self.exec.fs_read_file(conn, env_path, format="string") or "")
        except Exception:
            existing = ""
        lines = [
            line
            for line in existing.splitlines()
            if not any(line.startswith(f"{key}=") for key in managed)
        ]
        lines.extend(f"{key}={value}" for key, value in managed.items())
        self.exec.fs_write_file(conn, env_path, "\n".join(lines) + "\n")

    def _latest_dag_run(self, dag_id: str) -> dict[str, Any]:
        encoded_dag_id = urllib.parse.quote(dag_id, safe="")
        try:
            payload = self._airflow_api_get(
                f"/dags/{encoded_dag_id}/dagRuns",
                {
                    "limit": "1",
                    "order_by": "-logical_date",
                },
            )
        except Exception as exc:
            logger.info("Could not load latest Airflow DAG run for %s: %s", dag_id, exc)
            return {}
        runs = payload.get("dag_runs", [])
        if isinstance(runs, list) and runs:
            run = runs[0]
            return run if isinstance(run, dict) else {}
        return {}

    def _airflow_api_get(
        self,
        path: str,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for api_prefix in ("/api/v2", "/api/v1"):
            url = self._airflow_api_url(api_prefix, path, query)
            try:
                return self._urlopen_json(
                    url,
                    auth="bearer" if api_prefix == "/api/v2" else "basic",
                )
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in {401, 404}:
                    continue
                raise
            except urllib.error.URLError as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        raise RuntimeError("Airflow API request failed.")

    def _airflow_api_url(
        self,
        api_prefix: str,
        path: str,
        query: dict[str, str] | None,
    ) -> str:
        base_url = self.service_urls.get("Airflow UI", "").rstrip("/")
        if not base_url:
            raise ValueError("Airflow UI URL is not available.")
        normalized_path = "/" + path.lstrip("/")
        url = f"{base_url}{api_prefix}{normalized_path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        return url

    def _urlopen_json(self, url: str, *, auth: str = "basic") -> dict[str, Any]:
        ssl_context = ssl._create_unverified_context()
        request = urllib.request.Request(url)
        self._add_airflow_auth_header(request, auth)
        with urllib.request.urlopen(
            request,
            timeout=15,
            context=ssl_context,
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def _add_airflow_auth_header(
        self,
        request: urllib.request.Request,
        auth: str,
    ) -> None:
        if auth == "bearer":
            request.add_header("Authorization", f"Bearer {self._airflow_access_token()}")
            return

        auth_string = f"{self.ui_user}:{self.ui_pw}"
        encoded_auth = base64.b64encode(auth_string.encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {encoded_auth}")

    def _airflow_access_token(self) -> str:
        token = str(getattr(self, "_cached_airflow_access_token", "") or "")
        if token:
            return token

        base_url = self.service_urls.get("Airflow UI", "").rstrip("/")
        if not base_url:
            raise ValueError("Airflow UI URL is not available.")
        payload = json.dumps(
            {
                "username": self.ui_user,
                "password": self.ui_pw,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/auth/token",
            data=payload,
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        ssl_context = ssl._create_unverified_context()
        with urllib.request.urlopen(
            request,
            timeout=15,
            context=ssl_context,
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict) or not data.get("access_token"):
            raise ValueError("Airflow token response did not include an access token.")
        token = str(data["access_token"])
        setattr(self, "_cached_airflow_access_token", token)
        return token

    def _dag_schedule(self, dag: dict[str, Any]) -> str:
        schedule = (
            dag.get("timetable_summary")
            or dag.get("schedule_interval")
            or dag.get("schedule")
            or ""
        )
        if isinstance(schedule, dict):
            return str(
                schedule.get("value")
                or schedule.get("__type")
                or json.dumps(schedule, sort_keys=True)
            )
        return str(schedule or "-")

    def _dag_tags(self, tags: Any) -> str:
        if not isinstance(tags, list):
            return ""
        values = []
        for tag in tags:
            if isinstance(tag, dict):
                values.append(str(tag.get("name") or tag.get("tag_name") or ""))
            else:
                values.append(str(tag))
        return ", ".join(value for value in values if value)

    def _join_list(self, values: Any) -> str:
        if isinstance(values, list):
            return ", ".join(str(value) for value in values)
        return str(values or "")

    def get_secrets(self) -> Dict[str, Dict]:
        credentials = {
            "username": self.ui_user,
            "password": self.ui_pw,
            "port": self.port,
            "secret_key": self.secret_key,
            "secret_path": self.secret_path,
            "base_url": self.service_urls.get("Airflow UI", ""),
        }
        return {"airflow_ui_credentials": credentials}
