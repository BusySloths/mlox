"""Rebuild an encrypted MLOX project file from a printed ``MloxProject(...)`` dump.

The default input is ``./mlox_project_content.key`` and the script writes
``./recovered_mlox.project`` encrypted with the default password below.
"""

from __future__ import annotations

import argparse
import ast
import copy
from pathlib import Path
from typing import Any

from mlox.session import MloxProject
from mlox.utils import dataclass_to_dict, save_to_json

DEFAULT_INPUT_PATH = Path("mlox_project_content.key")
DEFAULT_PROJECT_NAME = "recovered_mlox"
DEFAULT_PROJECT_PASSWORD = "Recovered12345"

_INIT_FIELDS = {
    "name",
    "created_at",
    "last_opened_at",
    "secret_manager_class",
    "secret_manager_info",
}
_ASSIGNABLE_FIELDS = {"descr", "version"}
_SERVER_CLASS_BY_CONFIG_PREFIX = {
    "ubuntu-docker": "mlox.servers.ubuntu.docker.UbuntuDockerServer",
    "ubuntu-native": "mlox.servers.ubuntu.native.UbuntuNativeServer",
    "ubuntu-simple": "mlox.servers.ubuntu.simple.UbuntuSimpleServer",
    "ubuntu-k3s": "mlox.servers.ubuntu.k3s.UbuntuK3sServer",
    "local-server": "mlox.servers.local.local.LocalhostServer",
}


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Dict):
        return {
            _eval_node(key): _eval_node(value)
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.List):
        return [_eval_node(element) for element in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(element) for element in node.elts)
    if isinstance(node, ast.Set):
        return {_eval_node(element) for element in node.elts}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand)
    raise ValueError(f"Unsupported expression in dump: {ast.dump(node, include_attributes=False)}")


def _repair_server_dict_metadata(server_dict: dict[str, Any]) -> dict[str, Any]:
    if "_module_name_" in server_dict and "_class_name_" in server_dict:
        return server_dict

    repaired = copy.deepcopy(server_dict)
    service_config_id = str(repaired.get("service_config_id", ""))
    backend = repaired.get("backend", [])
    class_path = None

    for prefix, candidate in _SERVER_CLASS_BY_CONFIG_PREFIX.items():
        if service_config_id.startswith(prefix):
            class_path = candidate
            break

    if class_path is None and isinstance(backend, list):
        backend_set = set(backend)
        if "k3s" in backend_set or "kubernetes" in backend_set:
            class_path = _SERVER_CLASS_BY_CONFIG_PREFIX["ubuntu-k3s"]
        elif "docker" in backend_set:
            class_path = _SERVER_CLASS_BY_CONFIG_PREFIX["ubuntu-docker"]
        elif "native" in backend_set:
            class_path = _SERVER_CLASS_BY_CONFIG_PREFIX["ubuntu-native"]

    if class_path is None:
        raise ValueError(
            "Server configuration is missing class metadata and the concrete server type could not be inferred."
        )

    module_name, class_name = class_path.rsplit(".", 1)
    repaired["_module_name_"] = module_name
    repaired["_class_name_"] = class_name
    return repaired


def _repair_secret_manager_info(project: MloxProject) -> None:
    if project.secret_manager_class != "mlox.secret_manager.TinySecretManager":
        return
    keyfile = project.secret_manager_info.get("keyfile")
    if isinstance(keyfile, dict):
        project.secret_manager_info["keyfile"] = _repair_server_dict_metadata(keyfile)


def parse_project_dump(text: str) -> MloxProject:
    module = ast.parse(text.strip(), mode="eval")
    expr = module.body
    if not isinstance(expr, ast.Call):
        raise ValueError("Dump must be a single MloxProject(...) expression.")
    if not isinstance(expr.func, ast.Name) or expr.func.id != "MloxProject":
        raise ValueError("Dump must start with MloxProject(...).")
    if expr.args:
        raise ValueError("Positional arguments are not supported in project dumps.")

    raw_fields = {kw.arg: _eval_node(kw.value) for kw in expr.keywords if kw.arg}
    if "name" not in raw_fields:
        raise ValueError("Project dump is missing the 'name' field.")

    init_kwargs = {key: value for key, value in raw_fields.items() if key in _INIT_FIELDS}
    project = MloxProject(**init_kwargs)
    for field_name in _ASSIGNABLE_FIELDS:
        if field_name in raw_fields:
            setattr(project, field_name, raw_fields[field_name])
    _repair_secret_manager_info(project)
    return project


def recover_project(
    input_path: Path,
    project_name: str = DEFAULT_PROJECT_NAME,
    password: str = DEFAULT_PROJECT_PASSWORD,
) -> Path:
    project = parse_project_dump(input_path.read_text(encoding="utf-8"))
    project.name = project_name
    output_path = input_path.parent / f"{project_name}.project"
    save_to_json(dataclass_to_dict(project), str(output_path), password, encrypt=True)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recreate an encrypted .project file from a printed MloxProject dump."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Path to the dump file. Defaults to {DEFAULT_INPUT_PATH}.",
    )
    parser.add_argument(
        "--project-name",
        default=DEFAULT_PROJECT_NAME,
        help=f"Recovered project name. Defaults to {DEFAULT_PROJECT_NAME}.",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PROJECT_PASSWORD,
        help="Password used to encrypt the recovered .project file.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_path = recover_project(
        input_path=args.input,
        project_name=args.project_name,
        password=args.password,
    )
    print(
        f"Wrote {output_path} with project name '{args.project_name}' "
        f"and password '{args.password}'."
    )


if __name__ == "__main__":
    main()
