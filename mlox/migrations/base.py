import os
import logging

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from mlox.session import MloxSession

logger = logging.getLogger(__name__)


class MloxMigrations(ABC):
    """Handles migrations for MLOX projects."""

    name: str
    childs: List["MloxMigrations"] | None = None

    def _add_field_to_class(
        self,
        data: Dict[str, Any],
        module_name: str,
        class_name: str,
        field_name: str,
        default_value: Any,
    ) -> Dict[str, Any]:
        """
        Add a missing field to every dict representing the target dataclass.

        The target is identified by matching both ``_module_name_`` and
        ``_class_name_`` keys. Traversal is iterative (no recursion) to
        support nested structures produced by serialization.
        """

        stack: List[Any] = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if (
                    item.get("_module_name_") == module_name
                    and item.get("_class_name_") == class_name
                    and field_name not in item
                ):
                    logger.info(
                        "Adding field '%s' to %s.%s with default value '%s'.",
                        field_name,
                        module_name,
                        class_name,
                        default_value,
                    )
                    item[field_name] = default_value

                for value in item.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(item, list):
                for value in item:
                    if isinstance(value, (dict, list)):
                        stack.append(value)
        return data

    def _migrate_childs(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.childs:
            return data
        for child in self.childs:
            logger.info(
                f"Applying child migration: {child.name} for Migration {self.name}"
            )
            data = child.migrate(data)
        return data

    @abstractmethod
    def migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass


def load_mlox_session(migrations: List[MloxMigrations]) -> MloxSession:
    mlox_name = os.environ.get("MLOX_PROJECT_NAME", None)
    mlox_password = os.environ.get("MLOX_PROJECT_PASSWORD", None)
    # Make sure your environment variable is set!
    if not mlox_password or not mlox_name:
        print(
            "Error: MLOX_PROJECT_PASSWORD or MLOX_PROJECT_NAME environment variable is not set."
        )
        exit(1)
    return MloxSession(mlox_name, mlox_password, migrations=migrations)
