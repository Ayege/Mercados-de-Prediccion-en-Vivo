"""Controles de seguridad como tests: si alguien abre un hueco, falla antes del commit.

Cada test corresponde a un hallazgo o control de SECURITY.md.
"""

import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build, build_cloud, build_infra, build_service

KEY = "k" * 32
STATIC = Path(__file__).parents[2] / "app" / "entrypoints" / "http" / "static"
# Las únicas escrituras que la audiencia puede hacer. Cualquier ruta POST nueva que no
# esté aquí debe exigir la clave del ponente, o este archivo falla.
AUDIENCE_WRITES = {"/api/entrar", "/api/markets/{market_id}/trade", "/api/markets/{market_id}/census"}


def make(**overrides):
    base = Settings(
        **{
            **Settings().__dict__,
            "backend": "mock",
            "oracle_cooldown": 0,
            "presenter_key": KEY,
            "infra_mode": "ensayo",
            **overrides,
        }
    )
    cloud = build_cloud(base)
    infra = build_infra(base, cloud)
    service = build_service(base, cloud=cloud, infra=infra)
    app = build(base, service, cloud, infra, with_seed=False)
    app.state.service = service
    return app, TestClient(app), infra


@pytest.fixture()
def env():
    return make()


def market(client):
    r = client.post(
        "/api/markets",
        json={"question": "¿Pregunta segura?", "criteria": "SÍ si pasa."},
        headers={"X-Presenter-Key": KEY},
    )
    return r.json()["id"]


def room_code(client):
    return client.get("/api/sala", headers={"X-Presenter-Key": KEY}).json()["code"]


def enter(client, name):
    r = client.post("/api/entrar", json={"name": name, "code": room_code(client)})
    return r.json()["token"]


# --- A01 Control de acceso -----------------------------------------------------------


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Lecturas reservadas al ponente: revelan el código de sala o borradores sin publicar.
PRESENTER_READS = {"/api/sala", "/api/noticias"}


def concrete(path):
    return re.sub(r"\{[^}]+\}", "x", path)


def test_every_write_route_requires_the_presenter_unless_it_is_an_audience_write(env):
    app, client, _ = env
    writes = [(r, m) for r in app.routes if isinstance(r, APIRoute) for m in r.methods & WRITE_METHODS]
    assert len(writes) > 10 and any(m == "DELETE" for _, m in writes)
    for route, method in writes:
        if route.path in AUDIENCE_WRITES:
            continue
        status = client.request(method, concrete(route.path)).status_code
        assert status == 403, f"{method} {route.path} no exige la clave del ponente"


def test_presenter_reads_require_the_presenter(env):
    app, client, _ = env
    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert PRESENTER_READS <= paths
    for path in PRESENTER_READS:
        assert client.get(path).status_code == 403, f"{path} no exige la clave del ponente"


def test_entering_needs_the_room_code_shown_on_the_projector(env):
    _, client, _ = env
    assert client.post("/api/entrar", json={"name": "afuera"}).status_code == 401
    assert client.post("/api/entrar", json={"name": "afuera", "code": "XXXXXX"}).status_code == 401
    assert client.get("/api/info").json()["room_code_required"] is True
    assert "code" not in str(client.get("/api/info").json()).lower().replace("room_code_required", "")
    code = room_code(client)
    assert client.post("/api/entrar", json={"name": "adentro", "code": code.lower()}).status_code == 201


def test_production_refuses_to_start_without_a_room_code():
    s = Settings(**{**Settings().__dict__, "production": True, "presenter_key": KEY, "room_code": " "})
    with pytest.raises(RuntimeError, match="SALA_CODIGO"):
        s.check()


def test_anonymous_traffic_is_not_counted_as_demand(env):
    _, client, infra = env
    for _ in range(20):
        client.get("/api/markets")
        client.get("/api/users/nadie", headers={"X-User-Token": "falso"})
    assert infra._requests == 0
    token = enter(client, "aye")
    client.get("/api/users/aye", headers={"X-User-Token": token})
    assert infra._requests == 1


def test_presenter_actions_leave_an_audit_line(env):
    import logging

    class Collect(logging.Handler):
        def __init__(self):
            super().__init__()
            self.lines = []

        def emit(self, record):
            self.lines.append(record.getMessage())

    collect = Collect()
    logging.getLogger("oraculo.auditoria").addHandler(collect)
    try:
        _, client, _ = env
        market(client)
        client.post("/api/nube/iniciar", headers={"X-Presenter-Key": "mala"})  # el intento también queda
    finally:
        logging.getLogger("oraculo.auditoria").removeHandler(collect)
    lines = collect.lines
    assert any('"ruta": "/api/nube/iniciar"' in ln and '"estado": 403' in ln for ln in lines)
    assert any("/api/markets" in ln and "201" in ln and "ponente" in ln for ln in lines)
    assert KEY not in "".join(lines)


@pytest.mark.parametrize("path", ["/api/markets/x/trade", "/api/markets/x/census"])
def test_audience_writes_require_a_user_token(env, path):
    _, client, _ = env
    assert (
        client.post(path, json={"user": "aye", "outcome": "YES", "amount": 1, "answer": True}).status_code
        == 401
    )


def test_nobody_can_trade_with_someone_elses_name(env):
    _, client, _ = env
    mid = market(client)
    enter(client, "aye")
    mallory = enter(client, "mallory")
    r = client.post(
        f"/api/markets/{mid}/trade",
        json={"user": "aye", "outcome": "YES", "amount": 10},
        headers={"X-User-Token": mallory},
    )
    assert r.status_code == 401


def test_names_cannot_be_taken_twice(env):
    _, client, _ = env
    enter(client, "aye")
    assert client.post("/api/entrar", json={"name": "AYE", "code": room_code(client)}).status_code == 409


def test_balances_are_private(env):
    _, client, _ = env
    enter(client, "aye")
    assert client.get("/api/users/aye").status_code == 401


def test_public_infra_view_neither_keeps_nodes_alive_nor_runs_the_controller(env):
    _, client, infra = env
    before = infra.last_seen
    client.get("/api/infra")
    assert infra.last_seen == before and infra.state.last_cycle is None
    client.get("/api/infra", headers={"X-Presenter-Key": KEY})
    assert infra.last_seen > before and infra.state.last_cycle is not None


def test_scheduler_can_only_call_the_vigil_with_a_valid_oidc_token():
    app, client, _ = make()
    assert client.post("/api/infra/vigilia", headers={"Authorization": "Bearer falso"}).status_code == 403

    async def check(token):
        return token == "firmado-por-google"

    base = Settings(
        **{**Settings().__dict__, "backend": "mock", "presenter_key": KEY, "infra_mode": "ensayo"}
    )
    cloud = build_cloud(base)
    infra = build_infra(base, cloud)
    from app.entrypoints.http.api import create_app

    c = TestClient(
        create_app(build_service(base, cloud=cloud, infra=infra), cloud, infra, KEY, scheduler_check=check)
    )
    assert (
        c.post("/api/infra/vigilia", headers={"Authorization": "Bearer firmado-por-google"}).status_code
        == 200
    )
    assert (
        c.post(
            "/api/infra/actuar?activo=true", headers={"Authorization": "Bearer firmado-por-google"}
        ).status_code
        == 403
    )


# --- A02 Fallas criptográficas -----------------------------------------------------


def test_user_tokens_are_random_and_stored_only_as_hashes(env):
    app, client, _ = env
    t1, t2 = enter(client, "aye"), enter(client, "bob")
    assert t1 != t2 and len(t1) >= 32
    for account in app.state.service.repo.accounts():
        assert t1 not in vars(account).values() and t2 not in vars(account).values()
        assert len(account.credential) == 64  # sha256 en hexadecimal


# --- A03 Inyección -----------------------------------------------------------------


@pytest.mark.parametrize("name", ["<script>", 'a"b', "x" * 25, "", "a/b"])
def test_names_reject_markup_and_oversize(env, name):
    _, client, _ = env
    assert client.post("/api/entrar", json={"name": name}).status_code == 422


def test_pages_have_no_inline_scripts_or_handlers():
    for page in STATIC.glob("*.html"):
        html = page.read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), f"script en línea en {page.name}"
        assert not re.search(r"\son[a-z]+\s*=", html), f"manejador en línea en {page.name}"


def test_scripts_do_not_use_dynamic_code():
    for js in STATIC.glob("*.js"):
        code = js.read_text()
        for bad in ("eval(", "new Function", "document.write", 'setTimeout("', 'setInterval("'):
            assert bad not in code, f"{bad} en {js.name}"


# --- A04/A05 Diseño y configuración ------------------------------------------------


@pytest.mark.parametrize("path", ["/api/salud", "/api/markets", "/index.html"])
def test_security_headers_everywhere(env, path):
    _, client, _ = env
    h = client.get(path).headers
    assert "script-src 'self';" in h["content-security-policy"]
    assert "unsafe-inline" not in h["content-security-policy"].split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer"


def test_api_responses_are_not_cached(env):
    _, client, _ = env
    assert client.get("/api/markets").headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "overrides",
    [
        {"production": True, "presenter_key": ""},
        {"production": True, "presenter_key": "corta"},
        {"infra_mode": "real", "presenter_key": "corta"},
    ],
)
def test_production_refuses_to_start_without_a_strong_key(overrides):
    with pytest.raises(RuntimeError, match="PRESENTER_KEY"):
        Settings(**{**Settings().__dict__, **overrides}).check()


def test_api_docs_are_closed_in_production(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "oraculo-api")
    assert Settings.from_env().api_docs is False
    _, client, _ = make(api_docs=False)
    assert client.get("/api/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


# --- Disponibilidad y costo --------------------------------------------------------


def test_orders_are_rate_limited_per_person(env):
    _, client, _ = env
    mid = market(client)
    token = enter(client, "aye")
    codes = [
        client.post(
            f"/api/markets/{mid}/trade",
            json={"user": "aye", "outcome": "YES", "amount": 1},
            headers={"X-User-Token": token},
        ).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [200] * 10 and codes[-1] == 429


def test_public_view_hides_internal_errors(env):
    _, client, infra = env
    infra.state.last_error = (
        "no se pudo listar los nodos (RuntimeError: 403: Permission denied on projects/x)"
    )
    infra.state.last_cycle = infra.clock()  # que la consulta del ponente no dispare un ciclo nuevo
    assert "projects/x" not in client.get("/api/infra").text
    assert "projects/x" in client.get("/api/infra", headers={"X-Presenter-Key": KEY}).text
