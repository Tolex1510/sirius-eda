"""Правило зависимостей: слой бизнес-логики не знает о веб-фреймворке и ORM."""
import ast
from pathlib import Path

import pytest

FORBIDDEN = {"fastapi", "sqlalchemy", "starlette"}
SERVICES = sorted(Path(__file__).parent.parent.joinpath("app", "modules").glob("*/service.py"))


def imported_packages(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_all_modules_have_service():
    assert {p.parent.name for p in SERVICES} == {"users", "menu", "orders", "delivery"}


@pytest.mark.parametrize("path", SERVICES, ids=lambda p: p.parent.name)
def test_service_has_no_framework_imports(path):
    assert imported_packages(path) & FORBIDDEN == set()
