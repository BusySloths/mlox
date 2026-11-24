"""Process-owned groups of service forwards; no project data is mutated."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock, Timer
from typing import Any, Callable
from uuid import uuid4

from mlox.contracts.servers import ServerCapability
from mlox.tunnel import TunnelBinding, TunnelPlan


@dataclass
class TunnelGroup:
    id: str
    service_uuid: str
    bindings: tuple[TunnelBinding, ...]
    secrets: dict[str, Any] = field(repr=False)
    _resources: ExitStack = field(repr=False)
    expires_at: datetime | None = None
    _timer: Timer | None = field(default=None, repr=False)


class TunnelManager:
    """Own forwards for the process lifetime, closing partial groups on failure."""

    def __init__(self, resolve_server: Callable[[str], Any]) -> None:
        self._resolve_server = resolve_server
        self._groups: dict[str, TunnelGroup] = {}
        self._lock = RLock()
        self._shutdown = False

    def open(self, plan: TunnelPlan, make_secrets: Callable[[tuple[TunnelBinding, ...]], dict[str, Any]], *, duration: float | None = None) -> TunnelGroup:
        if duration is not None and (not 0 < duration <= 86400 * 30):
            raise ValueError("Tunnel duration must be positive and no more than 30 days.")
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Tunnel manager has been shut down.")
        with ExitStack() as resources:
            bindings = []
            for endpoint in plan.endpoints:
                server = self._resolve_server(endpoint.server_uuid)
                if (server is None or ServerCapability.TUNNEL not in getattr(server, "capabilities", set())
                        or not callable(getattr(server, "open_tunnel", None))):
                    raise ValueError(f"Server for endpoint {endpoint.name!r} does not support tunnels.")
                binding = resources.enter_context(server.open_tunnel(endpoint))
                if not isinstance(binding, TunnelBinding) or binding.endpoint != endpoint:
                    raise ValueError("Server returned an invalid tunnel binding.")
                bindings.append(binding)
            resolved = tuple(bindings)
            secrets = make_secrets(resolved)
            if not isinstance(secrets, dict):
                raise TypeError("Tunnel secrets must be a dictionary.")
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration) if duration is not None else None
            with self._lock:
                if self._shutdown:
                    secrets.clear()
                    raise RuntimeError("Tunnel manager has been shut down.")
                group = TunnelGroup(uuid4().hex, plan.service_uuid, resolved, secrets, resources.pop_all(), expires_at)
                self._groups[group.id] = group
                if duration is not None:
                    group._timer = Timer(duration, self.close, args=(group.id,))
                    group._timer.daemon = True
                    group._timer.start()
                return group

    def list_groups(self) -> tuple[TunnelGroup, ...]:
        with self._lock:
            return tuple(self._groups.values())

    def close(self, group_id: str) -> None:
        with self._lock:
            group = self._groups.pop(group_id, None)
        if group is None:
            return
        if group._timer is not None:
            group._timer.cancel()
        try:
            group._resources.close()
        finally:
            group.secrets.clear()

    def close_all(self) -> None:
        with self._lock:
            group_ids = tuple(self._groups)
        errors = []
        for group_id in group_ids:
            try:
                self.close(group_id)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Failed to close tunnel groups", errors)

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown = True
        self.close_all()
