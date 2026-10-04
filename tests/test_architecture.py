"""La regla de dependencias de clean architecture, verificada en cada push.

Las dependencias apuntan hacia adentro: entrypoints y adapters → application → domain.
Solo la raíz de composición (main, config, seeds) conoce todas las capas.
"""
import ast
from pathlib import Path

import pytest

APP = Path(__file__).parent.parent / "app"

# Qué capas del proyecto puede importar cada capa.
ALLOWED = {
    "domain": {"domain"},
    "application": {"domain", "application"},
    "adapters": {"domain", "application", "adapters"},
    "entrypoints": {"domain", "application", "entrypoints"},
}
# Librerías que no deben filtrarse hacia el centro.
FORBIDDEN_THIRD_PARTY = {
    "domain": {"fastapi", "pydantic", "httpx", "google", "starlette", "os"},
    "application": {"fastapi", "pydantic", "httpx", "google", "starlette", "os"},
}


def imports(path: Path) -> set[str]:
    """Módulos importados, resueltos a rutas absolutas del tipo `app.capa...`."""
    package = path.relative_to(APP.parent).with_suffix("").parts[:-1]
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level + 1]
                found.add(".".join([*base, node.module or ""]).rstrip("."))
            else:
                found.add(node.module or "")
    return found


def files(layer: str):
    return sorted((APP / layer).rglob("*.py"))


@pytest.mark.parametrize("layer", list(ALLOWED))
def test_layer_only_depends_inward(layer):
    for path in files(layer):
        for mod in imports(path):
            parts = mod.split(".")
            if parts[0] == "app":
                target = parts[1] if len(parts) > 1 else ""
                assert target in ALLOWED[layer], f"{path.relative_to(APP)} importa {mod}"


@pytest.mark.parametrize("layer", list(FORBIDDEN_THIRD_PARTY))
def test_core_has_no_framework_or_io(layer):
    for path in files(layer):
        for mod in imports(path):
            root = mod.split(".")[0]
            assert root not in FORBIDDEN_THIRD_PARTY[layer], f"{path.relative_to(APP)} importa {mod}"
