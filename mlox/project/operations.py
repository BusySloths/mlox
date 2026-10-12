"""Persisted project-level operations activity records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OperationsEvent:
    """One immutable event in the project's operations audit trail."""

    event_type: str
    summary: str
    actor: str = "system"
    target: str = ""
    status: str = "recorded"
    details: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class OperationsAgent:
    """A project-scoped Operations team member and its bounded authority."""

    name: str
    role: str
    scope: str
    description: str
    status: str = "inactive"
    runtime: str = "planned"
    id: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class OperationsAgentRun:
    """One durable unit of work assigned to an Operations agent."""

    agent_id: str
    summary: str
    status: str = "queued"
    pipeline_id: str = ""
    id: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class OperationsAgentMessage:
    """An instruction, observation, or response attached to an agent run."""

    run_id: str
    author: str
    kind: str
    content: str
    details: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class OperationsAgentProposal:
    """A reviewable recommendation produced by an Operations agent."""

    agent_id: str
    run_id: str
    headline: str
    description: str
    verification: str = ""
    actions: list[dict[str, Any]] = field(default_factory=list)
    status: str = "open"
    pipeline_id: str = ""
    id: str = ""
    created_at: str = ""
    updated_at: str = ""
