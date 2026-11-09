"""Server capability contracts."""

from enum import StrEnum


class ServerCapability(StrEnum):
    """User-facing server capabilities advertised by configs and classes."""

    HEALTH = "health"
    LOGS = "logs"
    GIT = "git"
    FIREWALL = "firewall"
    INITIAL_AUTH_PASSWORD = "initial_auth_password"
    TERMINAL = "terminal"
    NATIVE = "native"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    LOCAL = "local"
    CONNECTOR = "connector"
