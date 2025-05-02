import importlib
import json
import logging
import os

from dacite import from_dict
from dataclasses import asdict, is_dataclass
from typing import List, Any

from mlox.remote import exec_command


def execute_command(conn, cmd: List | str):
    if isinstance(cmd, str):
        # Type 1: single CMD executed as sudo
        exec_command(conn, cmd, sudo=True)
    if isinstance(cmd, list):
        if isinstance(cmd[0], bool):
            # Type 2: [Sudo True/False, CMD, Descr]
            exec_command(conn, cmd[1], sudo=cmd[0])
        else:
            # Type 3: Function call with arguments
            func_name = cmd[0]
            module_name = "mlox.remote"
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
            args = cmd[1:]
            print(f"Execute CMD: {func_name} with args: {args}")
            if args:
                func(conn, *args)
            else:
                func(conn)


def save_dataclass_to_json(obj: Any, path: str) -> None:
    """Saves a dataclass instance to a JSON file, including its class information."""
    if not is_dataclass(obj):
        raise TypeError("Object must be a dataclass instance")

    data = asdict(obj)
    # Add class metadata
    data["_module_name_"] = obj.__class__.__module__
    data["_class_name_"] = obj.__class__.__name__

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_dataclass_from_json(path: str) -> Any:
    """
    Loads a dataclass instance from a JSON file.
    Uses metadata (_module_name_, _class_name_) stored in the JSON
    to determine the concrete class to instantiate, ensuring it's a subclass
    of the provided base_cls.
    """

    print(os.getcwd() + path)
    with open(os.getcwd() + path, "r") as f:
        data = json.load(f)

    module_name = data.pop("_module_name_", None)
    class_name = data.pop("_class_name_", None)

    try:
        module = importlib.import_module(module_name)
        concrete_cls = getattr(module, class_name)

        # Use dacite with the dynamically determined concrete class
        # Pass the remaining data (without the metadata keys)
        return from_dict(
            data_class=concrete_cls, data=data
        )  # Add config=Config(...) if needed

    except (ImportError, AttributeError, TypeError) as e:
        logging.error(f"Error loading concrete class {module_name}.{class_name}: {e}")
        # Fallback or re-raise depending on desired behavior
        raise ValueError(
            f"Could not load dataclass from {path} due to class resolution error."
        ) from e
