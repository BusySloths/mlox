"""Generate repetitive Typer commands from explicit workspace command specs."""

from __future__ import annotations

import inspect
import types
from dataclasses import dataclass
from typing import Any, Callable, Literal, Union, get_args, get_origin, get_type_hints

import typer

from mlox.application.result import OperationResult
from mlox.cli.common import handle_result
from mlox.cli.context import resolve_credentials
from mlox.project import ProjectWorkspace


_INFER = object()
ParameterTransform = Callable[[Any], Any]
ResultRenderer = Callable[[OperationResult[Any]], None]


def _identity(value: Any) -> Any:
    return value


def _is_supported_annotation(annotation: Any) -> bool:
    """Return whether Typer can expose the annotation used by this generator."""

    if annotation in {str, int, float, bool}:
        return True
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is list:
        return len(arguments) == 1 and arguments[0] in {str, int, float, bool}
    if origin in {Union, types.UnionType}:
        concrete = tuple(item for item in arguments if item is not type(None))
        return len(concrete) == 1 and len(concrete) != len(arguments) and (
            _is_supported_annotation(concrete[0])
        )
    return False


@dataclass(frozen=True)
class CliParameter:
    """CLI presentation for one workspace method parameter."""

    name: str
    help: str
    kind: Literal["argument", "option"] = "option"
    target: str | None = None
    declarations: tuple[str, ...] = ()
    annotation: Any = _INFER
    default: Any = _INFER
    transform: ParameterTransform = _identity
    prompt: bool | str = False
    hide_input: bool = False
    show_default: bool = True

    @property
    def workspace_parameter(self) -> str:
        return self.target or self.name


@dataclass(frozen=True)
class WorkspaceCommand:
    """Explicit allowlisted mapping from one CLI command to a workspace method."""

    name: str
    method: str
    help: str
    renderer: ResultRenderer
    parameters: tuple[CliParameter, ...] = ()
    scope: Literal["workspace", "class"] = "workspace"


def _method_contract(spec: WorkspaceCommand):
    try:
        method = getattr(ProjectWorkspace, spec.method)
    except AttributeError as exc:
        raise ValueError(
            f"CLI command {spec.name!r} references unknown ProjectWorkspace "
            f"method {spec.method!r}."
        ) from exc
    if not callable(method):
        raise ValueError(
            f"CLI command {spec.name!r} references non-callable workspace "
            f"attribute {spec.method!r}."
        )
    return method, inspect.signature(method), get_type_hints(method)


def validate_workspace_command(spec: WorkspaceCommand) -> None:
    """Validate that a command manifest matches its workspace method signature."""

    _, signature, type_hints = _method_contract(spec)
    return_annotation = type_hints.get("return")
    if return_annotation is not OperationResult and (
        get_origin(return_annotation) is not OperationResult
    ):
        raise ValueError(
            f"CLI command {spec.name!r} requires ProjectWorkspace.{spec.method} "
            "to return OperationResult."
        )
    method_parameters = {
        name: parameter
        for name, parameter in signature.parameters.items()
        if name not in {"self", "cls"}
    }
    mapped_targets: set[str] = set()
    cli_names: set[str] = set()

    for parameter in spec.parameters:
        target = parameter.workspace_parameter
        if parameter.name in cli_names:
            raise ValueError(
                f"CLI command {spec.name!r} declares duplicate parameter "
                f"{parameter.name!r}."
            )
        if target in mapped_targets:
            raise ValueError(
                f"CLI command {spec.name!r} maps workspace parameter "
                f"{target!r} more than once."
            )
        if target not in method_parameters:
            raise ValueError(
                f"CLI command {spec.name!r} maps unknown parameter {target!r} "
                f"for ProjectWorkspace.{spec.method}."
            )
        cli_names.add(parameter.name)
        mapped_targets.add(target)

    missing = [
        name
        for name, parameter in method_parameters.items()
        if parameter.default is inspect.Parameter.empty and name not in mapped_targets
    ]
    if missing:
        names = ", ".join(missing)
        raise ValueError(
            f"CLI command {spec.name!r} does not map required workspace "
            f"parameter(s): {names}."
        )

    if spec.scope == "workspace" and "self" not in signature.parameters:
        raise ValueError(
            f"CLI command {spec.name!r} requires a bound workspace method."
        )
    if spec.scope == "class" and "self" in signature.parameters:
        raise ValueError(
            f"CLI command {spec.name!r} cannot call an instance method without "
            "a workspace."
        )


def _parameter_default(
    cli_parameter: CliParameter,
    workspace_parameter: inspect.Parameter,
) -> Any:
    if cli_parameter.default is not _INFER:
        return cli_parameter.default
    if workspace_parameter.default is not inspect.Parameter.empty:
        return workspace_parameter.default
    return ...


def _callback_parameter(
    cli_parameter: CliParameter,
    workspace_parameter: inspect.Parameter,
    type_hints: dict[str, Any],
) -> inspect.Parameter:
    annotation = (
        type_hints[cli_parameter.workspace_parameter]
        if cli_parameter.annotation is _INFER
        else cli_parameter.annotation
    )
    if not _is_supported_annotation(annotation):
        raise ValueError(
            f"CLI parameter {cli_parameter.name!r}, mapped to workspace parameter "
            f"{cli_parameter.workspace_parameter!r}, has unsupported annotation "
            f"{annotation!r}; provide a supported CLI annotation."
        )
    default = _parameter_default(cli_parameter, workspace_parameter)
    if cli_parameter.kind == "argument":
        parameter_info = typer.Argument(default, help=cli_parameter.help)
    else:
        declarations = cli_parameter.declarations or (
            f"--{cli_parameter.name.replace('_', '-')}",
        )
        parameter_info = typer.Option(
            default,
            *declarations,
            help=cli_parameter.help,
            prompt=cli_parameter.prompt,
            hide_input=cli_parameter.hide_input,
            show_default=cli_parameter.show_default,
        )
    return inspect.Parameter(
        cli_parameter.name,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        default=parameter_info,
        annotation=annotation,
    )


def build_workspace_command(spec: WorkspaceCommand) -> Callable[..., None]:
    """Build a Typer-compatible callback for an explicit workspace command."""

    validate_workspace_command(spec)
    _, method_signature, type_hints = _method_contract(spec)

    def callback(**values: Any) -> None:
        project = values.pop("project", None)
        password = values.pop("password", None)
        arguments = {
            parameter.workspace_parameter: parameter.transform(values[parameter.name])
            for parameter in spec.parameters
        }
        if spec.scope == "workspace":
            resolved_project, resolved_password = resolve_credentials(project, password)
            workspace = ProjectWorkspace.open(resolved_project, resolved_password)
            operation = getattr(workspace, spec.method)
        else:
            operation = getattr(ProjectWorkspace, spec.method)
        result = handle_result(operation(**arguments))
        spec.renderer(result)

    callback.__name__ = f"{spec.method}_{spec.name.replace('-', '_')}_command"
    callback.__doc__ = spec.help

    parameters: list[inspect.Parameter] = []
    if spec.scope == "workspace":
        parameters.extend(
            [
                inspect.Parameter(
                    "project",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Argument(None, help="Project name"),
                    annotation=str | None,
                ),
                inspect.Parameter(
                    "password",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Option(
                        None,
                        "--password",
                        help="Password for the project",
                        show_default=False,
                    ),
                    annotation=str | None,
                ),
            ]
        )
    for cli_parameter in spec.parameters:
        workspace_parameter = method_signature.parameters[
            cli_parameter.workspace_parameter
        ]
        parameters.append(
            _callback_parameter(cli_parameter, workspace_parameter, type_hints)
        )

    callback.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    callback.__annotations__ = {
        parameter.name: parameter.annotation for parameter in parameters
    }
    callback.__annotations__["return"] = None
    setattr(callback, "__workspace_command__", spec)
    return callback


def register_workspace_commands(
    app: typer.Typer,
    commands: tuple[WorkspaceCommand, ...],
) -> dict[str, Callable[..., None]]:
    """Validate, build, and register a group of generated workspace commands."""

    names: set[str] = set()
    callbacks: dict[str, Callable[..., None]] = {}
    for spec in commands:
        if spec.name in names:
            raise ValueError(f"Duplicate CLI command name {spec.name!r}.")
        names.add(spec.name)
        callback = build_workspace_command(spec)
        app.command(spec.name, help=spec.help)(callback)
        callbacks[spec.name] = callback
    return callbacks
