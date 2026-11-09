"""Keep capability contracts independent of higher-level runtime modules."""

import ast
import importlib.util
from pathlib import Path

import pytest


CONTRACTS = Path(__file__).resolve().parents[2] / "mlox" / "contracts"
FORBIDDEN = ("mlox.service", "mlox.server", "mlox.infra", "mlox.services", "mlox.servers")


def _is_forbidden(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN)


def _type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute)
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
        and test.attr == "TYPE_CHECKING"
    )


def _runtime_imports(source: str, package: str) -> list[str]:
    """Inspect module and class bodies, excluding type-only and function bodies."""
    imports: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            pass

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_If(self, node: ast.If) -> None:
            if _type_checking(node.test):
                for statement in node.orelse:
                    self.visit(statement)
            else:
                self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            imports.extend(alias.name for alias in node.names)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module = node.module or ""
            if node.level:
                module = importlib.util.resolve_name("." * node.level + module, package)
            imports.append(module)
            imports.extend(f"{module}.{alias.name}" for alias in node.names if alias.name != "*")

    Visitor().visit(ast.parse(source))
    return imports


def test_contract_modules_do_not_import_higher_layers_at_module_load():
    violations = []
    for path in sorted(CONTRACTS.rglob("*.py")):
        relative = path.relative_to(CONTRACTS.parent.parent).with_suffix("")
        parts = list(relative.parts)
        package = ".".join(parts[:-1])
        for imported in _runtime_imports(path.read_text(encoding="utf-8"), package):
            if _is_forbidden(imported):
                violations.append(f"{path.relative_to(CONTRACTS.parent.parent)}: {imported}")
    assert not violations, "Contract modules must not import higher layers at module load:\n" + "\n".join(violations)


@pytest.mark.parametrize("statement", [
    "import mlox.service",
    "from mlox import server",
    "from mlox.infra import Infrastructure",
    "from mlox.services.minio import docker",
    "class Contract:\n    import mlox.servers.local",
    "if True:\n    import mlox.service",
    "from ... import service",
])
def test_boundary_detects_runtime_import_forms(statement):
    assert any(_is_forbidden(name) for name in _runtime_imports(statement, "mlox.contracts.services"))


def test_boundary_allows_type_only_and_deferred_imports():
    source = '''
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from mlox.infra import Infrastructure
if typing.TYPE_CHECKING:
    import mlox.service
class Contract:
    def bind(self):
        from mlox.secret_manager import AbstractSecretManager
'''
    assert not any(_is_forbidden(name) for name in _runtime_imports(source, "mlox.contracts.services"))
