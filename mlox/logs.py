"""Backend-neutral contract for bounded, on-demand log retrieval."""

from abc import ABC, abstractmethod


class LogSource(ABC):
    """Expose named log sources and retrieve recent lines from one source."""

    @abstractmethod
    def log_labels(self) -> list[str]:
        """Return the available source labels without opening a connection."""

    @abstractmethod
    def log_tail(self, conn, label: str | None = None, tail: int = 200) -> str:
        """Fetch recent lines; reject unknown labels and non-positive tails."""


def supports_logs(target: object | None) -> bool:
    """Require an advertised capability and both log operations."""
    if target is None:
        return False
    capabilities = getattr(target, "capabilities", ()) or ()
    names = {getattr(value, "value", value) for value in capabilities}
    return (
        "logs" in names
        and callable(getattr(target, "log_labels", None))
        and callable(getattr(target, "log_tail", None))
    )
