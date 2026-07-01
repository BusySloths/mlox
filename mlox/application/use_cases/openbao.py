from __future__ import annotations

from typing import Any

from mlox.application.result import OperationResult
from mlox.secret_manager import get_encrypted_access_keyfile
from mlox.utils import generate_pw


APPLICATION_PERIOD_OPTIONS: dict[str, str] = {
    "1 hour": "1h",
    "8 hours": "8h",
    "24 hours": "24h",
    "7 days": "168h",
    "30 days": "720h",
    "90 days": "2160h",
}


def describe_openbao(infra, service) -> OperationResult:
    """Return OpenBao status and stored credential metadata."""

    passwords_generated = _ensure_application_passwords(service)

    manager = None
    token_error = ""
    token_ttl = int(getattr(service, "client_token_lease_duration", 0) or 0)
    if getattr(service, "client_token", ""):
        try:
            manager = service.get_secret_manager(infra)
            token_data = manager.lookup_self()
            token_ttl = int(token_data.get("ttl") or 0)
            service.client_token_lease_duration = token_ttl
            service.client_token_renewable = bool(
                token_data.get("renewable", service.client_token_renewable)
            )
        except Exception as exc:
            token_error = str(exc)

    try:
        status = (
            manager.seal_status()
            if manager is not None
            else service.get_root_secret_manager(infra).seal_status()
        )
    except Exception:
        try:
            status = service.get_root_secret_manager(infra).seal_status()
        except Exception:
            status = {}

    initialized = bool(status.get("initialized", bool(getattr(service, "root_token", ""))))
    sealed = bool(status.get("sealed", False)) if status else False
    service_token_expired = (
        not bool(getattr(service, "client_token", ""))
        or manager is None
        or bool(token_error)
        or token_ttl <= 0
    )
    return OperationResult(
        True,
        0,
        "OpenBao settings loaded.",
        {
            "status": {
                "initialized": initialized,
                "sealed": sealed,
                "client_token_ttl": token_ttl,
                "client_token_expired": service_token_expired,
                "client_token_error": token_error,
            },
            "access": {
                "address": getattr(service, "service_url", ""),
                "mount_path": getattr(service, "mount_path", "secret"),
                "userpass_path": getattr(service, "userpass_path", "userpass"),
                "admin_username": getattr(service, "admin_username", ""),
                "admin_password": getattr(service, "admin_password", ""),
                "client_token": getattr(service, "client_token", ""),
                "client_token_accessor": getattr(service, "client_token_accessor", ""),
                "client_token_renewable": bool(
                    getattr(service, "client_token_renewable", False)
                ),
            },
            "applications": _credential_rows(service),
            "passwords_generated": passwords_generated,
            "recovery": {
                "root_token": getattr(service, "root_token", ""),
                "unseal_key_count": len(getattr(service, "unseal_keys", []) or []),
            },
        },
    )


def rotate_client_token(infra, service) -> OperationResult:
    try:
        service.rotate_client_token(infra)
    except Exception as exc:
        return OperationResult(False, 2, f"Could not rotate OpenBao client token: {exc}")
    return OperationResult(True, 0, "OpenBao client token rotated.")


def create_application_credential(
    infra,
    service,
    *,
    application_name: str,
    period: str,
) -> OperationResult:
    try:
        credential = service.create_application_credential(
            application_name,
            infra,
            period=period,
        )
        credential["keyfile_password"] = credential.get("keyfile_password") or generate_pw(
            16
        )
    except Exception as exc:
        return OperationResult(
            False,
            3,
            f"Could not add OpenBao application credential: {exc}",
        )
    return OperationResult(
        True,
        0,
        f"Added OpenBao credential for {credential.get('application_name', application_name)}.",
        {"credential": credential},
    )


def refresh_application_credentials(infra, service) -> OperationResult:
    try:
        credentials = service.refresh_application_credentials(infra)
        _ensure_application_passwords(service)
    except Exception as exc:
        return OperationResult(
            False,
            4,
            f"Could not refresh OpenBao application credentials: {exc}",
        )
    return OperationResult(
        True,
        0,
        "OpenBao application credentials refreshed.",
        {"applications": _credential_rows_from_mapping(credentials)},
    )


def renew_application_credential(infra, service, application_name: str) -> OperationResult:
    try:
        service.renew_application_credential(application_name, infra)
    except Exception as exc:
        return OperationResult(
            False,
            5,
            f"Could not renew OpenBao credential for {application_name}: {exc}",
        )
    return OperationResult(
        True,
        0,
        f"Renewed OpenBao credential for {application_name}.",
    )


def revoke_application_credential(infra, service, application_name: str) -> OperationResult:
    try:
        service.revoke_application_credential(application_name, infra)
    except Exception as exc:
        return OperationResult(
            False,
            6,
            f"Could not revoke OpenBao credential for {application_name}: {exc}",
        )
    return OperationResult(
        True,
        0,
        f"Revoked OpenBao credential for {application_name}.",
    )


def create_application_keyfile(infra, service, application_name: str) -> OperationResult:
    credentials = getattr(service, "application_credentials", {}) or {}
    credential = credentials.get(application_name)
    if not credential:
        return OperationResult(
            False,
            10,
            f"No OpenBao credential is registered for {application_name}.",
        )
    password = _ensure_application_password(service, application_name, credential)
    period = str(credential.get("period") or "24h")
    try:
        keyfile_manager = service.create_keyfile_secret_manager(
            infra,
            application_name=application_name,
            period=period,
        )
        service.application_credentials[application_name][
            "keyfile_password"
        ] = password
        keyfile = get_encrypted_access_keyfile(keyfile_manager, password)
    except Exception as exc:
        return OperationResult(
            False,
            11,
            f"Could not create OpenBao keyfile for {application_name}: {exc}",
        )
    return OperationResult(
        True,
        0,
        f"Created OpenBao keyfile for {application_name}.",
        {
            "application": application_name,
            "filename": f"{application_name}.json",
            "keyfile": keyfile,
            "password": password,
        },
    )


def get_application_keyfile_password(service, application_name: str) -> OperationResult:
    credentials = getattr(service, "application_credentials", {}) or {}
    credential = credentials.get(application_name)
    if not credential:
        return OperationResult(
            False,
            12,
            f"No OpenBao credential is registered for {application_name}.",
        )
    password_generated = not bool(credential.get("keyfile_password"))
    password = _ensure_application_password(service, application_name, credential)
    return OperationResult(
        True,
        0,
        f"Loaded OpenBao keyfile password for {application_name}.",
        {
            "application": application_name,
            "password": password,
            "password_generated": password_generated,
        },
    )


def renew_application_keyfile_password(service, application_name: str) -> OperationResult:
    credentials = getattr(service, "application_credentials", {}) or {}
    credential = credentials.get(application_name)
    if not credential:
        return OperationResult(
            False,
            13,
            f"No OpenBao credential is registered for {application_name}.",
        )
    credential["keyfile_password"] = generate_pw(16)
    credentials[application_name] = credential
    service.application_credentials = credentials
    return OperationResult(
        True,
        0,
        f"Renewed OpenBao keyfile password for {application_name}.",
    )


def unseal_openbao(infra, service) -> OperationResult:
    unseal_keys = list(getattr(service, "unseal_keys", []) or [])
    if not unseal_keys:
        return OperationResult(False, 7, "OpenBao has no stored unseal keys.")
    try:
        manager = service.get_root_secret_manager(infra)
        status: dict[str, Any] = {}
        for unseal_key in unseal_keys:
            status = manager.unseal(unseal_key)
            if not bool(status.get("sealed", True)):
                break
    except Exception as exc:
        return OperationResult(False, 8, f"Could not unseal OpenBao: {exc}")
    if bool(status.get("sealed", True)):
        return OperationResult(False, 9, "OpenBao remained sealed.")
    return OperationResult(True, 0, "OpenBao unsealed.")


def _credential_rows(service) -> list[dict[str, Any]]:
    _ensure_application_passwords(service)
    return _credential_rows_from_mapping(
        getattr(service, "application_credentials", {}) or {}
    )


def _credential_rows_from_mapping(
    credentials: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for name, credential in sorted(credentials.items()):
        accessor = str(credential.get("accessor", ""))
        rows.append(
            {
                "application": name,
                "status": credential.get("status", "active"),
                "ttl": _format_ttl(credential.get("lease_duration")),
                "renewable": bool(credential.get("renewable", True)),
                "period": credential.get("period") or "-",
                "accessor": f"{accessor[:12]}..." if accessor else "-",
                "keyfile_password_status": "Set"
                if credential.get("keyfile_password")
                else "Missing",
            }
        )
    return rows


def _ensure_application_passwords(service) -> bool:
    credentials = getattr(service, "application_credentials", {}) or {}
    generated = False
    for application, credential in credentials.items():
        if not credential.get("keyfile_password"):
            generated = True
        _ensure_application_password(service, application, credential)
    return generated


def _ensure_application_password(
    service,
    application: str,
    credential: dict[str, Any],
) -> str:
    password = str(credential.get("keyfile_password") or "")
    if password:
        return password
    password = generate_pw(16)
    credential["keyfile_password"] = password
    getattr(service, "application_credentials", {})[application] = credential
    return password


def _format_ttl(seconds: int | str | None) -> str:
    try:
        value = int(seconds or 0)
    except (TypeError, ValueError):
        return "-"
    if value <= 0:
        return "expired"
    if value >= 86400:
        return f"{value // 86400}d"
    if value >= 3600:
        return f"{value // 3600}h"
    if value >= 60:
        return f"{value // 60}m"
    return f"{value}s"


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"
