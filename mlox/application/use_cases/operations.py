"""Observe telemetry workloads and compare live signals with a normal baseline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import re
import statistics
from typing import Any

import requests

from mlox.application.result import OperationResult
from mlox.application.use_cases.services import (
    service_can_restart,
    service_has_health,
)
from mlox.project.entries import Entry, add_item, default_template, parse_board
from mlox.project.operations import OperationsAgent, OperationsEvent


OBSERVATION_PREFIX = "mlox.observation."
OPERATIONS_BOARD_TITLE = "Operations"
OPERATIONS_REASONING_SECRET = "mlox.operations.reasoning"
REASONING_MODES = {"disabled", "advisory", "approval"}

DEFAULT_OPERATIONS_AGENT = {
    "id": "pipeline-observer",
    "name": "Pipeline Observer",
    "role": "Observer",
    "status": "enabled",
    "scope": "Watched pipelines",
    "description": "Detects anomalies, gathers evidence and proposes reviewable actions.",
    "runtime": "active",
}


def list_operations_agents(workspace) -> OperationResult:
    """Return the durable experimental Operations roster."""

    list_agents = getattr(workspace, "list_operations_agents", None)
    if not callable(list_agents):
        return OperationResult(
            True, 0, "Using the default Operations roster.", {"agents": [DEFAULT_OPERATIONS_AGENT]}
        )
    try:
        stored = list_agents()
    except Exception as exc:
        return OperationResult(False, 56, f"Could not load Operations agents: {exc}")
    overrides = {agent.id: agent for agent in stored if isinstance(agent, OperationsAgent)}
    observer_override = overrides.pop(DEFAULT_OPERATIONS_AGENT["id"], None)
    observer = dict(DEFAULT_OPERATIONS_AGENT)
    if observer_override is not None:
        observer["status"] = observer_override.status
        observer["updated_at"] = observer_override.updated_at
    agents = [observer]
    for agent in overrides.values():
        if isinstance(agent, OperationsAgent):
            agents.append(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "role": agent.role,
                    "scope": agent.scope,
                    "description": agent.description,
                    "status": agent.status,
                    "runtime": agent.runtime,
                    "created_at": agent.created_at,
                    "updated_at": agent.updated_at,
                }
            )
    return OperationResult(True, 0, "Operations roster loaded.", {"agents": agents})


def save_operations_agent(workspace, *, name: str, role: str) -> OperationResult:
    """Add a disabled role profile without granting runtime authority yet."""

    name = str(name).strip()[:80]
    role = str(role).strip()
    if not name or role not in {"Investigator", "Planner", "Executor", "Auditor"}:
        return OperationResult(False, 57, "Choose an agent name and supported role.")
    save_agent = getattr(workspace, "save_operations_agent", None)
    list_agents = getattr(workspace, "list_operations_agents", None)
    if not callable(save_agent) or not callable(list_agents):
        return OperationResult(False, 40, "Project workspace is unavailable.")
    try:
        count = sum(1 for agent in list_agents() if agent.role == role)
        saved = save_agent(
            OperationsAgent(
                id=f"{role.lower()}-{count + 1}",
                name=name,
                role=role,
                status="disabled",
                scope="Not assigned",
                description="Role profile saved; runtime is not implemented yet.",
                runtime="planned",
            )
        )
    except Exception as exc:
        return OperationResult(False, 58, f"Could not save Operations agent: {exc}")
    return OperationResult(True, 0, f"Added {name} as a disabled {role}.", {"id": saved.id})


def archive_operations_agent(workspace, *, agent_id: str) -> OperationResult:
    """Archive a configurable agent profile while retaining its configuration."""

    if agent_id == DEFAULT_OPERATIONS_AGENT["id"]:
        return OperationResult(False, 59, "The built-in Pipeline Observer cannot be archived.")
    archive_agent = getattr(workspace, "archive_operations_agent", None)
    if not callable(archive_agent):
        return OperationResult(False, 40, "Project workspace is unavailable.")
    try:
        if archive_agent(agent_id):
            return OperationResult(True, 0, "Archived Operations agent.")
    except Exception as exc:
        return OperationResult(False, 60, f"Could not archive Operations agent: {exc}")
    return OperationResult(False, 61, "Operations agent was not found.")


def set_operations_agent_status(
    workspace, *, agent_id: str, enabled: bool
) -> OperationResult:
    """Enable or disable a profile without granting new authority."""

    set_status = getattr(workspace, "set_operations_agent_status", None)
    save_agent = getattr(workspace, "save_operations_agent", None)
    if not callable(set_status):
        return OperationResult(False, 40, "Project workspace is unavailable.")
    status = "enabled" if enabled else "disabled"
    try:
        if agent_id == DEFAULT_OPERATIONS_AGENT["id"]:
            if not callable(save_agent):
                return OperationResult(False, 40, "Project workspace is unavailable.")
            save_agent(OperationsAgent(**{**DEFAULT_OPERATIONS_AGENT, "status": status}))
            return OperationResult(True, 0, f"Pipeline Observer {status}.")
        if set_status(agent_id, status):
            return OperationResult(True, 0, f"Operations agent {status}.")
    except Exception as exc:
        return OperationResult(False, 63, f"Could not update Operations agent: {exc}")
    return OperationResult(False, 61, "Operations agent was not found or is archived.")


def _services(workspace) -> list[Any]:
    """Return the project's configured services without assuming a concrete workspace."""

    infrastructure = getattr(workspace, "infrastructure", None)
    services = getattr(infrastructure, "services", None)
    return list(services()) if callable(services) else []


def _model_rollback_choices(
    workspace, pipeline: dict[str, Any] | None
) -> list[dict[str, str]]:
    """Find safe previous registered-model versions for an observed workload."""

    if not pipeline:
        return []
    model_name = str(
        pipeline.get("model_name")
        or pipeline.get("subject_name")
        or ""
    ).strip()
    current_version = str(
        pipeline.get("model_version")
        or pipeline.get("subject_version")
        or ""
    ).strip()
    if not model_name or not current_version.isdigit():
        return []
    infrastructure = getattr(workspace, "infrastructure", None)
    filter_by_group = getattr(infrastructure, "filter_by_group", None)
    try:
        registries = (
            list(filter_by_group("model-registry")) if callable(filter_by_group) else []
        )
    except Exception:
        return []
    choices: list[dict[str, str]] = []
    for registry in registries:
        list_models = getattr(registry, "list_models", None)
        if not callable(list_models):
            continue
        try:
            versions = {
                str(item.get("Version"))
                for item in list_models()
                if str(item.get("Model") or "") == model_name
                and str(item.get("Version") or "").isdigit()
                and int(str(item["Version"])) < int(current_version)
            }
        except Exception:
            continue
        for version in sorted(versions, key=int, reverse=True):
            choices.append(
                {
                    "registry_name": str(getattr(registry, "name", "")),
                    "model_name": model_name,
                    "alias": str(pipeline.get("model_alias") or "champion"),
                    "target_version": version,
                }
            )
    return choices


def operations_remediation_tools(
    workspace, pipeline: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Describe the executable, approval-gated operations actions available now.

    The schemas are derived from real MLOX service and registry operations. They
    are sent to an OpenAI-compatible model as function tools, but are never
    invoked while reasoning. A person must explicitly choose Execute in the TUI.
    """

    services = _services(workspace)
    restartable = [
        str(service.name)
        for service in services
        if service_can_restart(service) and str(getattr(service, "name", ""))
    ]
    health_checkable = [
        str(service.name)
        for service in services
        if service_has_health(service) and str(getattr(service, "name", ""))
    ]
    tools: list[dict[str, Any]] = []
    if health_checkable:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "check_service_health",
                    "description": (
                        "Run the configured MLOX health check for one service. "
                        "Use this to verify a suspected dependency or recovery."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {
                                "type": "string",
                                "enum": health_checkable,
                                "description": "Configured service to inspect.",
                            }
                        },
                        "required": ["service_name"],
                        "additionalProperties": False,
                    },
                },
            }
        )
    if restartable:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "restart_service",
                    "description": (
                        "Restart or repair one configured MLOX service. This is a "
                        "mutating action and requires an explicit human approval."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {
                                "type": "string",
                                "enum": restartable,
                                "description": "Configured service to restart.",
                            }
                        },
                        "required": ["service_name"],
                        "additionalProperties": False,
                    },
                },
            }
        )
    rollback_choices = _model_rollback_choices(workspace, pipeline)
    if rollback_choices:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "rollback_model_alias",
                    "description": (
                        "Move a registered-model alias to a known earlier version. "
                        "Use only when the incident is consistent with a model "
                        "deployment regression. This is a mutating action and requires "
                        "an explicit human approval."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            key: {
                                "type": "string",
                                "enum": sorted({choice[key] for choice in rollback_choices}),
                            }
                            for key in (
                                "registry_name",
                                "model_name",
                                "alias",
                                "target_version",
                            )
                        },
                        "required": [
                            "registry_name",
                            "model_name",
                            "alias",
                            "target_version",
                        ],
                        "additionalProperties": False,
                    },
                },
                "x-mlox-valid-choices": rollback_choices,
            }
        )
    return tools


def _strip_reasoning(content: str) -> str:
    """Keep the answer after a reasoning-model's optional ``<think>`` block."""

    answer = content.rsplit("</think>", 1)[-1].strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", answer, flags=re.DOTALL)
    return fenced.group(1).strip() if fenced else answer


def _recommendation_content(content: str) -> dict[str, str]:
    """Normalize the compact JSON response while tolerating plain text models."""

    answer = _strip_reasoning(content)
    try:
        decoded = json.loads(answer)
    except (TypeError, json.JSONDecodeError):
        decoded = {}
    if isinstance(decoded, dict):
        headline = str(decoded.get("headline") or "Recommended remediation").strip()
        description = str(decoded.get("description") or "").strip()
        verification = str(decoded.get("verification") or "").strip()
        if description:
            return {
                "headline": headline[:120],
                "description": description[:1200],
                "verification": verification[:600],
            }
    first_line = next((line.strip() for line in answer.splitlines() if line.strip()), "")
    return {
        "headline": (first_line or "Recommended remediation")[:120],
        "description": answer[:1200],
        "verification": "Verify recovery against the rolling telemetry windows.",
    }


def _tool_only_recommendation(actions: list[dict[str, Any]]) -> dict[str, str] | None:
    """Provide a reviewable result for providers that omit text with tool calls."""

    if not actions:
        return None
    action = actions[0]
    name = str(action.get("name") or "")
    arguments = action.get("arguments") or {}
    if name == "rollback_model_alias":
        headline = "Roll back model version"
        description = (
            f"Move {arguments.get('model_name', 'the model')} alias "
            f"{arguments.get('alias', 'champion')} to version "
            f"{arguments.get('target_version', '-')}."
        )
    elif name == "restart_service":
        headline = "Restart service"
        description = f"Restart {arguments.get('service_name', 'the selected service')}."
    elif name == "check_service_health":
        headline = "Check service health"
        description = f"Check {arguments.get('service_name', 'the selected service')}."
    else:
        headline = "Review proposed MLOX action"
        description = "The reasoning assistant proposed a supported MLOX action."
    return {
        "headline": headline,
        "description": description,
        "verification": "Verify recovery against the rolling telemetry windows.",
    }


def _provider_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove MLOX-only metadata before sending OpenAI-compatible tools."""

    return [
        {key: value for key, value in tool.items() if not key.startswith("x-mlox-")}
        for tool in tools
    ]


def _reasoning_error_message(error: Exception, api_key: str) -> str:
    """Return a useful provider error without revealing the configured secret."""

    message = str(error)
    response = getattr(error, "response", None)
    body = str(getattr(response, "text", "") or "").strip()
    if api_key:
        message = message.replace(api_key, "[redacted]")
        body = body.replace(api_key, "[redacted]")
    if body and body not in message:
        message = f"{message}: {body[:600]}"
    return message[:800]


def _requested_tools(
    message: dict[str, Any], available: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate model function calls against the exact schemas offered to it."""

    allowed = {
        str(tool["function"]["name"]): tool
        for tool in available
        if isinstance(tool.get("function"), dict)
    }
    requested: list[dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "")
        if name not in allowed:
            continue
        try:
            arguments = json.loads(str(function.get("arguments") or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(arguments, dict):
            continue
        parameters = allowed[name]["function"]["parameters"]
        properties = parameters.get("properties", {})
        required = parameters.get("required", [])
        if any(key not in arguments for key in required):
            continue
        if any(
            key not in properties
            or (
                properties[key].get("enum")
                and str(value) not in properties[key]["enum"]
            )
            for key, value in arguments.items()
        ):
            continue
        choice_set = allowed[name].get("x-mlox-valid-choices")
        if choice_set and {
            key: str(arguments[key]) for key in required
        } not in choice_set:
            continue
        requested.append(
            {
                "name": name,
                "arguments": {key: str(arguments[key]) for key in required},
            }
        )
    return requested


def _reasoning_defaults() -> dict[str, Any]:
    return {
        "mode": "disabled",
        "provider": "openai-compatible",
        "endpoint": "",
        "model": "",
        "api_key_configured": False,
    }


def load_operations_reasoning_settings(workspace) -> OperationResult:
    """Load redacted reasoning-assistant settings from the active secret manager."""

    settings = _reasoning_defaults()
    manager = getattr(workspace, "secrets", None)
    if manager is None:
        return OperationResult(False, 40, "Project secret manager is unavailable.")
    try:
        stored = manager.load_secret(OPERATIONS_REASONING_SECRET)
    except Exception as exc:
        return OperationResult(False, 41, f"Could not load reasoning settings: {exc}")
    if stored is None:
        return OperationResult(True, 0, "Reasoning assistant is not configured.", settings)
    if not isinstance(stored, dict):
        return OperationResult(False, 42, "Stored reasoning settings are invalid.")
    for key in ("mode", "provider", "endpoint", "model"):
        if key in stored:
            settings[key] = str(stored[key])
    settings["api_key_configured"] = bool(stored.get("api_key"))
    return OperationResult(True, 0, "Reasoning settings loaded.", settings)


def save_operations_reasoning_settings(
    workspace,
    *,
    mode: str,
    provider: str,
    endpoint: str,
    model: str,
    api_key: str = "",
) -> OperationResult:
    """Persist reasoning settings without returning or logging the API key."""

    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in REASONING_MODES:
        return OperationResult(False, 43, "Unknown reasoning-assistant mode.")
    manager = getattr(workspace, "secrets", None)
    if manager is None:
        return OperationResult(False, 40, "Project secret manager is unavailable.")
    try:
        existing = manager.load_secret(OPERATIONS_REASONING_SECRET)
        existing_key = existing.get("api_key", "") if isinstance(existing, dict) else ""
        stored = {
            "mode": normalized_mode,
            "provider": str(provider).strip() or "openai-compatible",
            "endpoint": str(endpoint).strip(),
            "model": str(model).strip(),
            "api_key": str(api_key).strip() or existing_key,
        }
        manager.save_secret(OPERATIONS_REASONING_SECRET, stored)
    except Exception as exc:
        return OperationResult(False, 44, f"Could not save reasoning settings: {exc}")
    redacted = {key: value for key, value in stored.items() if key != "api_key"}
    redacted["api_key_configured"] = bool(stored["api_key"])
    return OperationResult(True, 0, "Reasoning settings saved.", redacted)


def reason_about_operations_incident(
    workspace,
    pipeline: dict[str, Any],
    *,
    post=None,
) -> OperationResult:
    """Ask the configured OpenAI-compatible model for advisory remediation."""

    manager = getattr(workspace, "secrets", None)
    if manager is None:
        return OperationResult(False, 40, "Project secret manager is unavailable.")
    try:
        settings = manager.load_secret(OPERATIONS_REASONING_SECRET)
    except Exception as exc:
        return OperationResult(False, 41, f"Could not load reasoning settings: {exc}")
    if not isinstance(settings, dict):
        return OperationResult(False, 46, "Reasoning assistant is not configured.")
    endpoint = str(settings.get("endpoint") or "").strip().rstrip("/")
    model = str(settings.get("model") or "").strip()
    if not endpoint or not model:
        return OperationResult(
            False,
            47,
            "Reasoning endpoint and model must be configured.",
        )
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    evidence = {
        "workload": pipeline.get("pipeline_name"),
        "subject": {
            "kind": pipeline.get("subject_kind") or "model",
            "name": pipeline.get("subject_name") or pipeline.get("model_name"),
            "version": pipeline.get("subject_version") or pipeline.get("model_version"),
        },
        "state": pipeline.get("state"),
        "likely_origin": pipeline.get("culprit"),
        "quality_metric": pipeline.get("quality_name"),
        "quality_value": pipeline.get("quality_value"),
        "steps": pipeline.get("steps") or [],
    }
    headers = {"Content-Type": "application/json"}
    api_key = str(settings.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = post or requests.post
    tools = operations_remediation_tools(workspace, pipeline)
    provider_tools = _provider_tools(tools)
    request_payload: dict[str, Any] = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the restricted Pipeline Observer for an MLOX operations "
                    "team. Assess only the supplied telemetry evidence. First identify "
                    "the affected pipeline step and propose a focused investigation of "
                    "that step. Return a compact JSON object with: "
                    "`headline` (an imperative solution title, at most 80 "
                    "characters), `description` (one to three concise sentences), "
                    "and `verification` (one concise recovery check). Use a tool "
                    "call only when one of the supplied MLOX actions is relevant; "
                    "when a supplied model-alias rollback is a credible response "
                    "to a model deployment regression, propose that concrete action "
                    "as an optional rollback, not as an executed fact. "
                    "never invent a tool. Tool calls are proposals only: never "
                    "claim an action was executed."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(evidence, sort_keys=True, default=str),
            },
        ],
    }
    if provider_tools:
        request_payload["tools"] = provider_tools
        request_payload["tool_choice"] = "auto"
    try:
        response = request(
            endpoint,
            headers=headers,
            json=request_payload,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["choices"][0]["message"]
        if not isinstance(message, dict):
            raise ValueError("The model returned an invalid message.")
        actions = _requested_tools(message, tools)
        recommendation = _recommendation_content(str(message.get("content") or ""))
        if not recommendation["description"]:
            recommendation = _tool_only_recommendation(actions) or recommendation
        if not recommendation["description"]:
            raise ValueError("The model returned an empty recommendation.")
    except Exception as exc:
        return OperationResult(
            False,
            48,
            f"Incident reasoning failed: {_reasoning_error_message(exc, api_key)}",
        )
    return OperationResult(
        True,
        0,
        "Reasoning recommendation received.",
        {
            "recommendation": recommendation["description"],
            "headline": recommendation["headline"],
            "verification": recommendation["verification"],
            "actions": actions,
            "mode": "advisory",
            "model": model,
        },
    )


def ask_operations_agent(
    workspace,
    *,
    agent: dict[str, Any],
    question: str,
    post=None,
) -> OperationResult:
    """Ask one configured Operations agent a non-mutating, project-scoped question."""

    manager = getattr(workspace, "secrets", None)
    if manager is None:
        return OperationResult(False, 40, "Project secret manager is unavailable.")
    try:
        settings = manager.load_secret(OPERATIONS_REASONING_SECRET)
    except Exception as exc:
        return OperationResult(False, 41, f"Could not load reasoning settings: {exc}")
    if not isinstance(settings, dict):
        return OperationResult(False, 46, "Reasoning assistant is not configured.")
    endpoint = str(settings.get("endpoint") or "").strip().rstrip("/")
    model = str(settings.get("model") or "").strip()
    if not endpoint or not model:
        return OperationResult(False, 47, "Reasoning endpoint and model must be configured.")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    api_key = str(settings.get("api_key") or "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = post or requests.post
    name = str(agent.get("name") or "Operations agent")
    role = str(agent.get("role") or "Advisor")
    scope = str(agent.get("scope") or "the configured operations scope")
    description = str(agent.get("description") or "")
    try:
        response = request(
            endpoint,
            headers=headers,
            json={
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"You are {name}, a restricted {role} in an MLOX Operations "
                            f"team. Your focus is {scope}. {description} Give a concise, "
                            "evidence-oriented answer. Do not claim to execute actions or "
                            "invent project state; suggestions require human approval."
                        ),
                    },
                    {"role": "user", "content": str(question).strip()},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        answer = _strip_reasoning(str(payload["choices"][0]["message"].get("content") or ""))
        if not answer:
            raise ValueError("The model returned an empty answer.")
    except Exception as exc:
        return OperationResult(
            False, 64, f"Agent question failed: {_reasoning_error_message(exc, api_key)}"
        )
    return OperationResult(True, 0, "Agent answer received.", {"answer": answer[:2400], "model": model})


def execute_operations_remediation(
    workspace,
    actions: list[dict[str, Any]],
    *,
    pipeline: dict[str, Any] | None = None,
) -> OperationResult:
    """Execute explicitly approved remediation actions selected by the user.

    This deliberately accepts only the same narrow action set advertised to the
    model. It does not execute a free-form model instruction.
    """

    offered = {
        tool["function"]["name"]: tool
        for tool in operations_remediation_tools(workspace, pipeline)
    }
    if not actions:
        return OperationResult(False, 49, "There are no proposed MLOX actions to execute.")
    messages: list[str] = []
    for action in actions:
        name = str(action.get("name") or "")
        arguments = action.get("arguments") or {}
        tool = offered.get(name)
        if not tool:
            return OperationResult(False, 50, f"Unsupported remediation action: {name}.")
        parameters = tool["function"]["parameters"]
        required = parameters.get("required", [])
        properties = parameters.get("properties", {})
        if any(key not in arguments for key in required) or any(
            key not in properties
            or (
                properties[key].get("enum")
                and str(value) not in properties[key]["enum"]
            )
            for key, value in arguments.items()
        ):
            return OperationResult(False, 51, "Remediation action has an invalid service target.")
        valid_choices = tool.get("x-mlox-valid-choices")
        if valid_choices and {
            key: str(arguments[key]) for key in required
        } not in valid_choices:
            return OperationResult(False, 51, "Remediation action has an invalid rollback target.")
        try:
            if name == "check_service_health":
                result = workspace.check_service_health(
                    name=str(arguments["service_name"])
                )
            elif name == "restart_service":
                result = workspace.restart_service(name=str(arguments["service_name"]))
            elif name == "rollback_model_alias":
                result = _rollback_model_alias(workspace, arguments)
            else:  # Defensive guard if the advertised registry grows later.
                return OperationResult(False, 50, f"Unsupported remediation action: {name}.")
        except Exception as exc:
            return OperationResult(False, 52, f"Remediation action failed: {exc}")
        if not result.success:
            return OperationResult(False, result.code, result.message)
        messages.append(result.message)
    return OperationResult(True, 0, " ".join(messages), {"actions": actions})


def _rollback_model_alias(workspace, arguments: dict[str, Any]) -> OperationResult:
    """Move one MLflow registry alias after explicit Operations approval."""

    infrastructure = getattr(workspace, "infrastructure", None)
    get_service = getattr(infrastructure, "get_service", None)
    registry = (
        get_service(str(arguments["registry_name"])) if callable(get_service) else None
    )
    if registry is None:
        return OperationResult(False, 54, "The selected model registry is unavailable.")
    try:
        direct = getattr(registry, "set_registered_model_alias", None)
        if callable(direct):
            direct(
                name=str(arguments["model_name"]),
                alias=str(arguments["alias"]),
                version=str(arguments["target_version"]),
            )
        else:
            from mlox.services.mlflow.registry_client import create_mlflow_client

            secrets = registry.get_secrets()
            client = create_mlflow_client(
                str(secrets.get("service_url") or ""),
                str(secrets.get("username") or ""),
                str(secrets.get("password") or ""),
            )
            client.set_registered_model_alias(
                name=str(arguments["model_name"]),
                alias=str(arguments["alias"]),
                version=str(arguments["target_version"]),
            )
    except Exception as exc:
        return OperationResult(False, 55, f"Could not roll back the model alias: {exc}")
    return OperationResult(
        True,
        0,
        f"Moved {arguments['model_name']} alias {arguments['alias']} to version "
        f"{arguments['target_version']}.",
    )


def get_operations_board(workspace, *, create: bool = False) -> OperationResult:
    """Load the Knowledge board reserved for operations planning."""

    find_entry = getattr(workspace, "find_entry_by_title", None)
    save_entry = getattr(workspace, "save_entry", None)
    if not callable(find_entry):
        return OperationResult(False, 45, "Project knowledge base is unavailable.")
    board = find_entry(OPERATIONS_BOARD_TITLE, "board")
    if board is None and create:
        if not callable(save_entry):
            return OperationResult(False, 45, "Project knowledge base is unavailable.")
        board = save_entry(
            Entry(
                kind="board",
                title=OPERATIONS_BOARD_TITLE,
                body_md=default_template("board", OPERATIONS_BOARD_TITLE),
            )
        )
    message = (
        "Operations board loaded."
        if board is not None
        else "No Knowledge board named 'Operations' exists yet."
    )
    return OperationResult(True, 0, message, {"board": board})


def add_operations_plan_item(
    workspace,
    *,
    headline: str,
    description: str,
) -> OperationResult:
    """Add a concise, human-reviewed remediation proposal to the Operations board."""

    board_result = get_operations_board(workspace, create=True)
    if not board_result.success:
        return board_result
    board = (board_result.data or {}).get("board")
    save_entry = getattr(workspace, "save_entry", None)
    if board is None or not callable(save_entry):
        return OperationResult(False, 45, "Project knowledge base is unavailable.")
    columns = parse_board(board.body_md)
    if not columns:
        return OperationResult(False, 53, "The Operations board has no markdown columns.")
    compact_description = " ".join(str(description).split())[:280]
    card = str(headline).strip()[:120]
    if compact_description:
        card = f"{card} — {compact_description}"
    board.body_md = add_item(board.body_md, 0, card)
    saved = save_entry(board)
    return OperationResult(True, 0, "Recommendation added to the Operations plan.", {"board": saved})


def save_operations_postmortem(
    workspace,
    pipeline: dict[str, Any],
    events: list[OperationsEvent],
) -> OperationResult:
    """Save a deterministic incident postmortem and link it from the plan board."""

    save_entry = getattr(workspace, "save_entry", None)
    if not callable(save_entry):
        return OperationResult(False, 45, "Project knowledge base is unavailable.")
    pipeline_name = str(pipeline.get("pipeline_name") or "observed workload")
    timestamp = datetime.now(timezone.utc)
    title_prefix = f"Postmortem - {pipeline_name} - {timestamp:%Y-%m-%d %H:%M:%S UTC}"
    existing_titles = {entry.title for entry in workspace.list_entries("wiki")}
    title = title_prefix
    duplicate_number = 2
    while title in existing_titles:
        title = f"{title_prefix} ({duplicate_number})"
        duplicate_number += 1
    culprit = str(pipeline.get("culprit") or "Not determined")
    quality_name = str(pipeline.get("quality_name") or "quality metric")
    quality_value = pipeline.get("quality_value")
    timeline = "\n".join(
        f"- {event.created_at}: **{event.event_type}** — {event.summary}"
        for event in reversed(events)
        if event.target == str(pipeline.get("id") or "")
    ) or "- No persisted incident events were available."
    body = (
        "## Summary\n\n"
        f"Workload `{pipeline_name}` entered an anomalous state and later recovered.\n\n"
        "## Impact\n\n"
        f"Latest {quality_name}: `{quality_value if quality_value is not None else '-'}`.\n\n"
        "## Likely origin\n\n"
        f"`{culprit}`\n\n"
        "## Timeline\n\n"
        f"{timeline}\n\n"
        "## Remediation\n\n"
        "Recovery was verified through the rolling windows. Review the incident "
        "activity trail for proposed and manually applied remediation.\n\n"
        "## Follow-up actions\n\n"
        "- [ ] Review detection thresholds and baseline coverage.\n"
        "- [ ] Confirm the production rollback or traffic-control runbook.\n"
    )
    entry = save_entry(Entry(kind="wiki", title=title, body_md=body))
    board_result = get_operations_board(workspace, create=True)
    board = (board_result.data or {}).get("board") if board_result.success else None
    if board is not None:
        columns = parse_board(board.body_md)
        if columns:
            board.body_md = add_item(board.body_md, 0, f"Review [[{title}]] follow-ups")
            save_entry(board)
    return OperationResult(
        True,
        0,
        f"Postmortem saved to Knowledge as '{title}'.",
        {"entry": entry, "board": board},
    )


def _attributes(attributes: Any) -> dict[str, Any]:
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except json.JSONDecodeError:
            return {}
    if isinstance(attributes, dict):
        return {str(key): value for key, value in attributes.items()}
    values: dict[str, Any] = {}
    for item in attributes or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        encoded = item.get("value") or {}
        value = next(iter(encoded.values()), None) if isinstance(encoded, dict) else None
        values[str(item["key"])] = value
    return values


def _influx_span_to_otlp(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize an Influx exporter span row to the OTLP shape Operations uses."""
    trace_id = str(row.get("traceId") or row.get("trace_id") or "")
    span_id = str(row.get("spanId") or row.get("span_id") or "")
    name = str(row.get("name") or row.get("span.name") or "")
    if not trace_id or not span_id or not name:
        return None

    attributes = _attributes(row.get("attributes"))
    for key in ("service.name", "span.kind"):
        if key in row:
            attributes.setdefault(key, row[key])

    try:
        end_ns = int(
            row.get("endTimeUnixNano") or row.get("end_time_unix_nano") or 0
        )
    except (TypeError, ValueError):
        end_ns = 0
    try:
        start_ns = int(
            row.get("startTimeUnixNano") or row.get("start_time_unix_nano") or 0
        )
    except (TypeError, ValueError):
        start_ns = 0
    try:
        duration_ns = int(row.get("durationNano") or row.get("duration_nano") or 0)
    except (TypeError, ValueError):
        duration_ns = 0

    if not start_ns and end_ns and duration_ns:
        start_ns = end_ns - duration_ns
    if not end_ns and start_ns and duration_ns:
        end_ns = start_ns + duration_ns
    if not start_ns and row.get("time"):
        try:
            timestamp = datetime.fromisoformat(
                str(row["time"]).replace("Z", "+00:00")
            )
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            start_ns = (
                int(timestamp.timestamp()) * 1_000_000_000
                + timestamp.microsecond * 1_000
            )
        except (TypeError, ValueError, OverflowError):
            start_ns = 0
    if not end_ns:
        end_ns = start_ns + max(duration_ns, 0)

    return {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": attributes,
    }


def _spans(raw: str | None) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        for resource in payload.get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                spans.extend(scope.get("spans", []))
    return spans


def _numeric_observations(attributes: dict[str, Any]) -> dict[str, float]:
    observations: dict[str, float] = {}
    for key, value in attributes.items():
        if not key.startswith(OBSERVATION_PREFIX):
            continue
        if key.endswith((".dimensions", ".size")):
            continue
        try:
            observations[key.removeprefix(OBSERVATION_PREFIX)] = float(value)
        except (TypeError, ValueError):
            continue
    return observations


@dataclass(frozen=True)
class PipelineStepRun:
    span_id: str
    path: str
    name: str
    depth: int
    started_ns: int
    duration_ms: float
    labels: dict[str, Any]
    observations: dict[str, float]


@dataclass(frozen=True)
class PipelineRun:
    trace_id: str
    span_id: str
    pipeline_id: str
    model_name: str
    model_version: str
    model_alias: str
    subject_kind: str
    subject_name: str
    subject_version: str
    pipeline_name: str
    request_id: str
    started_ns: int
    labels: dict[str, Any]
    steps: tuple[PipelineStepRun, ...]


@dataclass
class OperationsWatchSession:
    """Bounded, in-memory baseline and incident analysis for observed workloads."""

    baseline_runs: int = 10
    max_runs: int = 200
    active: bool = False
    state: str = "stopped"
    model_name: str = ""
    monitor_uuid: str = ""
    monitor_name: str = ""
    runs: list[PipelineRun] = field(default_factory=list)
    seen_span_ids: set[str] = field(default_factory=set)
    _pending: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(dict), repr=False
    )
    incident_pipelines: set[tuple[str, str, str]] = field(default_factory=set)

    def start(self, raw: str | None) -> None:
        """Start after the current telemetry watermark; earlier data is ignored."""

        self.active = True
        self.state = "calibrating"
        self.model_name = ""
        self.runs.clear()
        self._pending.clear()
        self.incident_pipelines.clear()
        self.seen_span_ids = {
            str(span.get("spanId")) for span in _spans(raw) if span.get("spanId")
        }

    def stop(self) -> None:
        self.active = False

    def ingest(self, raw: str | None) -> int:
        if not self.active:
            return 0
        for span in _spans(raw):
            span_id = str(span.get("spanId") or "")
            trace_id = str(span.get("traceId") or "")
            if not span_id or not trace_id or span_id in self.seen_span_ids:
                continue
            self.seen_span_ids.add(span_id)
            self._pending[trace_id][span_id] = span

        completed: list[PipelineRun] = []
        for trace_id, spans_by_id in list(self._pending.items()):
            spans = list(spans_by_id.values())
            if not any(
                span.get("name") in {"mlox.model.live_predict", "mlox.workload.run"}
                for span in spans
            ):
                continue
            run = self._pipeline_run(trace_id, spans)
            if run is None:
                continue
            del self._pending[trace_id]
            completed.append(run)

        completed.sort(key=lambda run: run.started_ns)
        self.runs.extend(completed)
        grouped = self._grouped_runs()
        self.runs = sorted(
            (run for runs in grouped.values() for run in runs[-self.max_runs:]),
            key=lambda run: run.started_ns,
        )
        if self.runs:
            self.model_name = self.runs[-1].model_name
        self._update_state()
        return len(completed)

    def _pipeline_run(
        self, trace_id: str, spans: list[dict[str, Any]]
    ) -> PipelineRun | None:
        roots = [
            span
            for span in spans
            if span.get("name") in {"mlox.model.live_predict", "mlox.workload.run"}
        ]
        steps: list[PipelineStepRun] = []
        for span in spans:
            if span.get("name") not in {"mlox.model.step", "mlox.workload.step"}:
                continue
            attrs = _attributes(span.get("attributes"))
            path = str(attrs.get("mlox.step.path") or "")
            if not path:
                continue
            started_ns = int(span.get("startTimeUnixNano") or 0)
            ended_ns = int(span.get("endTimeUnixNano") or 0)
            duration_ms = max(0.0, (ended_ns - started_ns) / 1_000_000)
            observations = _numeric_observations(attrs)
            if ended_ns > started_ns:
                observations["execution.duration_ms"] = duration_ms
            steps.append(
                PipelineStepRun(
                    span_id=str(span.get("spanId") or ""),
                    path=path,
                    name=str(attrs.get("mlox.step.name") or path.rsplit("/", 1)[-1]),
                    depth=int(attrs.get("mlox.step.depth") or 1),
                    started_ns=started_ns,
                    duration_ms=duration_ms,
                    labels={
                        key: value
                        for key, value in attrs.items()
                        if not key.startswith(OBSERVATION_PREFIX)
                    },
                    observations=observations,
                )
            )
        if not roots or not steps:
            return None
        root = min(roots, key=lambda span: int(span.get("startTimeUnixNano") or 0))
        attrs = _attributes(root.get("attributes"))
        steps.sort(key=lambda step: step.started_ns)
        model_name = str(attrs.get("mlox.model.name") or "")
        model_version = str(attrs.get("mlox.model.version") or "")
        subject_name = str(
            attrs.get("mlox.subject.name")
            or attrs.get("mlox.workload.subject.name")
            or model_name
            or attrs.get("service.name")
            or "unknown"
        )
        subject_version = str(
            attrs.get("mlox.subject.version")
            or attrs.get("mlox.workload.subject.version")
            or model_version
            or ""
        )
        subject_kind = str(
            attrs.get("mlox.subject.kind")
            or attrs.get("mlox.workload.subject.kind")
            or ("model" if model_name else "workload")
        )
        return PipelineRun(
            trace_id=trace_id,
            span_id=str(root.get("spanId") or ""),
            pipeline_id=str(attrs.get("mlox.pipeline.id") or ""),
            model_name=model_name or "unknown",
            model_version=model_version or "unknown",
            model_alias=str(attrs.get("mlox.model.alias") or ""),
            subject_kind=subject_kind,
            subject_name=subject_name,
            subject_version=subject_version or "unknown",
            pipeline_name=str(
                attrs.get("mlox.pipeline.name")
                or attrs.get("mlox.workload.name")
                or "observed workload"
            ),
            request_id=str(attrs.get("mlox.request.id") or ""),
            started_ns=int(root.get("startTimeUnixNano") or 0),
            labels=attrs,
            steps=tuple(steps),
        )

    @staticmethod
    def _key(run: PipelineRun) -> tuple[str, str, str]:
        return run.subject_name, run.subject_version, run.pipeline_name

    def _grouped_runs(self) -> dict[tuple[str, str, str], list[PipelineRun]]:
        grouped: dict[tuple[str, str, str], list[PipelineRun]] = defaultdict(list)
        for run in self.runs:
            grouped[self._key(run)].append(run)
        return grouped

    def _baseline(
        self, runs: list[PipelineRun]
    ) -> dict[tuple[str, str], list[float]]:
        baseline: dict[tuple[str, str], list[float]] = defaultdict(list)
        for run in runs[: self.baseline_runs]:
            for step in run.steps:
                for name, value in step.observations.items():
                    if math.isfinite(value):
                        baseline[(step.path, name)].append(value)
        return baseline

    @staticmethod
    def _is_anomalous(value: float, baseline: list[float]) -> bool:
        if not baseline or not math.isfinite(value):
            return False
        center = statistics.median(baseline)
        deviations = [abs(point - center) for point in baseline]
        mad = statistics.median(deviations)
        spread = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
        tolerance = max(6.0 * mad, 4.0 * spread, abs(center) * 0.25, 1e-6)
        return abs(value - center) > tolerance

    @staticmethod
    def _window_average(
        runs: list[PipelineRun],
        step_path: str,
        observation_name: str,
        *,
        duration_ns: int,
        max_samples: int,
    ) -> float | None:
        if not runs:
            return None
        cutoff = runs[-1].started_ns - duration_ns
        values: list[float] = []
        for run in reversed(runs):
            if run.started_ns < cutoff:
                break
            for step in run.steps:
                if step.path == step_path and observation_name in step.observations:
                    value = step.observations[observation_name]
                    if math.isfinite(value):
                        values.append(value)
                    break
            if len(values) >= max_samples:
                break
        return statistics.mean(values) if values else None

    def _step_rows(self, runs: list[PipelineRun]) -> list[dict[str, Any]]:
        if not runs:
            return []
        baseline = self._baseline(runs)
        latest = runs[-1]
        rows: list[dict[str, Any]] = []
        for step in latest.steps:
            comparisons = []
            for name, value in step.observations.items():
                reference = baseline.get((step.path, name), [])
                if reference:
                    short_window = self._window_average(
                        runs,
                        step.path,
                        name,
                        duration_ns=60 * 1_000_000_000,
                        max_samples=5,
                    )
                    long_window = self._window_average(
                        runs,
                        step.path,
                        name,
                        duration_ns=5 * 60 * 1_000_000_000,
                        max_samples=10,
                    )
                    comparisons.append(
                        {
                            "name": name,
                            "baseline": statistics.median(reference),
                            "current": value,
                            "short_window": short_window,
                            "long_window": long_window,
                            "anomalous": any(
                                candidate is not None
                                and self._is_anomalous(candidate, reference)
                                for candidate in (short_window, long_window)
                            ),
                        }
                    )
            anomalous = any(item["anomalous"] for item in comparisons)
            rows.append(
                {
                    "path": step.path,
                    "name": step.name,
                    "depth": step.depth,
                    "state": "anomalous" if anomalous else "normal",
                    "observations": comparisons,
                }
            )
        return rows

    def _pipeline_state(
        self, key: tuple[str, str, str], runs: list[PipelineRun]
    ) -> str:
        if len(runs) < self.baseline_runs:
            return "calibrating"
        anomalous = any(
            row["state"] == "anomalous" for row in self._step_rows(runs)
        )
        if anomalous:
            self.incident_pipelines.add(key)
            return "incident"
        if key in self.incident_pipelines:
            return "recovered"
        return "watching"

    def _update_state(self) -> None:
        states = [
            self._pipeline_state(key, runs)
            for key, runs in self._grouped_runs().items()
        ]
        if not states:
            self.state = "calibrating"
        elif "incident" in states:
            self.state = "incident"
        elif "calibrating" in states:
            self.state = "calibrating"
        elif "recovered" in states:
            self.state = "recovered"
        else:
            self.state = "watching"

    @staticmethod
    def _quality_metric(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        preferred = ("rmse", "mae", "mse", "error", "accuracy", "f1", "precision", "recall")
        observations = [
            observation
            for row in rows
            if row.get("name") == "quality.evaluate"
            for observation in row.get("observations", [])
        ]
        if not observations:
            observations = [
                observation
                for row in rows
                for observation in row.get("observations", [])
            ]
        return next(
            (
                observation
                for metric in preferred
                for observation in observations
                if str(observation.get("name", "")).lower().startswith(metric)
            ),
            None,
        )

    def _pipeline_snapshot(
        self, key: tuple[str, str, str], runs: list[PipelineRun]
    ) -> dict[str, Any]:
        state = self._pipeline_state(key, runs)
        rows = self._step_rows(runs)
        culprit = next(
            (
                row["path"]
                for row in rows
                if row["state"] == "anomalous"
                and row["name"] != "quality.evaluate"
            ),
            next(
                (row["path"] for row in rows if row["state"] == "anomalous"),
                "",
            ),
        )
        quality = self._quality_metric(rows)
        subject_name, subject_version, pipeline_name = key
        latest = runs[-1]
        return {
            "id": "\x1f".join(key),
            "pipeline_name": pipeline_name,
            # Legacy fields are retained for existing model callers. New user
            # interfaces should use subject_* so the watcher also fits jobs,
            # data pipelines, and other instrumented workloads.
            "model_name": latest.model_name,
            "model_version": latest.model_version,
            "subject_kind": latest.subject_kind,
            "subject_name": subject_name,
            "subject_version": subject_version,
            "state": state,
            "runs": len(runs),
            "baseline_runs": min(len(runs), self.baseline_runs),
            "baseline_target": self.baseline_runs,
            "steps": rows,
            "culprit": culprit,
            "quality_name": quality.get("name") if quality else "",
            "quality_value": quality.get("long_window") if quality else None,
            "quality_current": quality.get("current") if quality else None,
            "quality_baseline": quality.get("baseline") if quality else None,
            "details": {
                "trace_id": latest.trace_id,
                "span_id": latest.span_id,
                "pipeline_id": latest.pipeline_id,
                "pipeline_name": latest.pipeline_name,
                "request_id": latest.request_id,
                "model_name": latest.model_name,
                "model_version": latest.model_version,
                "model_alias": latest.model_alias,
                "subject_kind": latest.subject_kind,
                "subject_name": latest.subject_name,
                "subject_version": latest.subject_version,
                "started_ns": latest.started_ns,
                "labels": latest.labels,
                "steps": [
                    {
                        "span_id": step.span_id,
                        "path": step.path,
                        "name": step.name,
                        "depth": step.depth,
                        "started_ns": step.started_ns,
                        "duration_ms": step.duration_ms,
                        "labels": step.labels,
                        "observations": step.observations,
                    }
                    for step in latest.steps
                ],
            },
        }

    def snapshot(self) -> dict[str, Any]:
        pipelines = [
            self._pipeline_snapshot(key, runs)
            for key, runs in self._grouped_runs().items()
        ]
        pipelines.sort(key=lambda item: (item["pipeline_name"], item["subject_name"]))
        primary = pipelines[0] if pipelines else {}
        return {
            "active": self.active,
            "state": self.state,
            "model_name": primary.get("model_name", self.model_name),
            "runs": len(self.runs),
            "baseline_runs": primary.get("baseline_runs", 0),
            "baseline_target": self.baseline_runs,
            "steps": primary.get("steps", []),
            "culprit": primary.get("culprit", ""),
            "latest_rmse": primary.get("quality_current"),
            "baseline_rmse": primary.get("quality_baseline"),
            "pipelines": pipelines,
        }


def list_operations_monitors(infra) -> list[dict[str, str]]:
    """Return services with a bounded telemetry-query backend for Operations."""

    monitors: list[dict[str, str]] = []
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if callable(getattr(service, "get_telemetry_query_service", None)):
                monitors.append(
                    {
                        "uuid": str(getattr(service, "uuid", "")),
                        "name": str(getattr(service, "name", "Telemetry monitor")),
                        "state": str(getattr(service, "state", "unknown")),
                        "bundle": str(getattr(bundle, "name", "-")),
                        "server": str(
                            getattr(getattr(bundle, "server", None), "ip", "-")
                        ),
                    }
                )
    return monitors


def _telemetry_source(
    infra, monitor_uuid: str | None = None
) -> tuple[Any, Any] | tuple[None, None]:
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if not callable(getattr(service, "get_telemetry_query_service", None)):
                continue
            if monitor_uuid and str(getattr(service, "uuid", "")) != monitor_uuid:
                continue
            return bundle, service
    return None, None


def _query_spans(service, *, since_seconds: int = 86_400) -> str:
    """Fetch Operations evidence through its backend, never collector files."""
    backend = service.get_telemetry_query_service()
    rows = backend.recent_spans(since_seconds=since_seconds, limit=500)
    payloads: list[str] = []
    for row in rows:
        # Influx stores spans as flattened rows (snake_case IDs/timestamps,
        # span.name, and JSON attributes); convert those rows back to the
        # normalized OTLP shape consumed by OperationsWatchSession.
        document = row.get("span") or row.get("data") or row
        if isinstance(document, str):
            try:
                document = json.loads(document)
            except json.JSONDecodeError:
                continue
        if isinstance(document, dict) and "resourceSpans" in document:
            payloads.append(json.dumps(document))
        elif isinstance(document, dict):
            span = (
                document
                if document.get("spanId")
                else _influx_span_to_otlp(document)
            )
            if span is not None:
                payloads.append(
                    json.dumps(
                        {"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}
                    )
                )
    return "\n".join(payloads)


def start_operations_watch(
    infra,
    *,
    baseline_runs: int = 10,
    monitor_uuid: str | None = None,
) -> OperationResult:
    bundle, service = _telemetry_source(infra, monitor_uuid)
    if bundle is None or service is None:
        message = (
            "The selected telemetry monitor is no longer available."
            if monitor_uuid
            else "No telemetry collector is available."
        )
        return OperationResult(False, 30, message)
    try:
        raw = _query_spans(service)
    except Exception as exc:
        return OperationResult(False, 31, f"Could not query telemetry: {exc}")
    session = OperationsWatchSession(baseline_runs=baseline_runs)
    session.monitor_uuid = str(getattr(service, "uuid", ""))
    session.monitor_name = str(getattr(service, "name", "Telemetry monitor"))
    session.start(raw)
    return OperationResult(
        True,
        0,
        "Operations watch started; existing telemetry was ignored.",
        {"session": session, "snapshot": session.snapshot()},
    )


def refresh_operations_watch(infra, session: OperationsWatchSession) -> OperationResult:
    bundle, service = _telemetry_source(infra, session.monitor_uuid or None)
    if bundle is None or service is None:
        return OperationResult(
            False, 30, "The selected telemetry monitor is no longer available."
        )
    try:
        raw = _query_spans(service)
        ingested = session.ingest(raw)
    except Exception as exc:
        return OperationResult(False, 31, f"Could not query telemetry: {exc}")
    return OperationResult(
        True,
        0,
        f"Operations watch ingested {ingested} new run(s).",
        {"snapshot": session.snapshot()},
    )
