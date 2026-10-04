import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build, build_service


def app_with(with_seed=False, **overrides):
    settings = Settings.from_env()
    settings = Settings(**{**settings.__dict__, "oracle_cooldown": 0, "backend": "mock", **overrides})
    return TestClient(build(settings, build_service(settings), with_seed=with_seed))


@pytest.fixture()
def client():
    return app_with()


def new_market(client):
    r = client.post(
        "/api/markets", json={"question": "¿Llueve mañana en SDQ?", "criteria": "SÍ si llueve."}
    )
    assert r.status_code == 201
    return r.json()["id"]


def trade(client, mid, user, outcome, amount):
    return client.post(
        f"/api/markets/{mid}/trade", json={"user": user, "outcome": outcome, "amount": amount}
    )


def test_trade_moves_price_and_balance(client):
    mid = new_market(client)
    body = trade(client, mid, "aye", "YES", 100).json()
    assert body["market"]["prices"]["YES"] > 0.5
    assert body["user"]["balance"] == 900


def test_insufficient_balance_is_rejected(client):
    mid = new_market(client)
    assert trade(client, mid, "aye", "YES", 5000).status_code == 400


def test_resolution_pays_winners(client, monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "YES")
    mid = new_market(client)
    shares = trade(client, mid, "aye", "YES", 100).json()["shares"]
    trade(client, mid, "bob", "NO", 100)
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["status"] == "resolved" and m["outcome"] == "YES"
    assert client.get("/api/users/aye").json()["balance"] == pytest.approx(900 + shares)
    assert client.get("/api/users/bob").json()["balance"] == pytest.approx(900)


def test_unresolved_keeps_market_open(client, monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "UNRESOLVED")
    mid = new_market(client)
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["status"] == "open" and m["oracle"]["outcome"] == "UNRESOLVED"


def test_cannot_trade_after_resolution(client, monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "NO")
    mid = new_market(client)
    client.post(f"/api/markets/{mid}/resolve")
    assert trade(client, mid, "aye", "YES", 10).status_code == 400


def test_oracle_cooldown(monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "UNRESOLVED")
    c = app_with(oracle_cooldown=60)
    mid = new_market(c)
    assert c.post(f"/api/markets/{mid}/resolve").status_code == 200
    assert c.post(f"/api/markets/{mid}/resolve").status_code == 429


def test_unknown_market_is_404(client):
    assert client.get("/api/markets/nope").status_code == 404


def test_seeded_app_serves_markets_and_health():
    c = app_with(with_seed=True)
    assert len(c.get("/api/markets").json()) == 3
    assert c.get("/healthz").json() == {"ok": True}


def sala_market(client, threshold=0.5):
    r = client.post("/api/markets", json={
        "question": "¿Más de la mitad desplegó un viernes?", "criteria": "Censo de la sala.",
        "kind": "sala", "threshold": threshold,
    })
    assert r.status_code == 201
    return r.json()["id"]


def test_resolution_records_room_belief_at_that_moment(client, monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "NO")
    mid = new_market(client)
    belief = trade(client, mid, "aye", "YES", 300).json()["market"]["prices"]["YES"]
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["oracle"]["price_yes"] == pytest.approx(belief)
    assert m["attempts"][0]["outcome"] == "NO" and m["attempts"][0]["sources"] == 2


def test_refusals_accumulate_in_attempts(client, monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "YES")
    mid = new_market(client)
    for fault in ("baja_confianza", "un_dominio", "json_malformado", "red_caida"):
        m = client.post(f"/api/markets/{mid}/resolve", params={"fault": fault}).json()
        assert m["status"] == "open"
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert [a["outcome"] for a in m["attempts"]] == ["UNRESOLVED"] * 4 + ["YES"]
    assert [a["fault"] for a in m["attempts"]][:4] == [
        "baja_confianza", "un_dominio", "json_malformado", "red_caida"]


def test_unknown_fault_is_422(client):
    mid = new_market(client)
    assert client.post(f"/api/markets/{mid}/resolve", params={"fault": "x"}).status_code == 422


def test_census_resolves_room_market(client):
    mid = sala_market(client)
    for i, answer in enumerate([True, True, True, False, False, True]):
        assert client.post(f"/api/markets/{mid}/census",
                           json={"user": f"u{i}", "answer": answer}).status_code == 200
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["status"] == "resolved" and m["outcome"] == "YES"
    assert m["oracle"]["model"] == "censo"


def test_census_below_minimum_stays_open(client):
    mid = sala_market(client)
    client.post(f"/api/markets/{mid}/census", json={"user": "aye", "answer": True})
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["status"] == "open" and m["oracle"]["outcome"] == "UNRESOLVED"


def test_census_is_one_answer_per_person(client):
    mid = sala_market(client)
    client.post(f"/api/markets/{mid}/census", json={"user": "aye", "answer": True})
    r = client.post(f"/api/markets/{mid}/census", json={"user": "AYE", "answer": False})
    assert r.status_code == 400


def test_census_rejected_on_oracle_market(client):
    mid = new_market(client)
    r = client.post(f"/api/markets/{mid}/census", json={"user": "aye", "answer": True})
    assert r.status_code == 400


def test_census_answers_are_not_exposed(client):
    mid = sala_market(client)
    client.post(f"/api/markets/{mid}/census", json={"user": "aye", "answer": True})
    m = client.get(f"/api/markets/{mid}").json()
    assert m["census_count"] == 1 and "census" not in m


def test_presenter_key_guards_create_and_resolve(monkeypatch):
    monkeypatch.setenv("PRESENTER_KEY", "s3creto")
    c = app_with(with_seed=True)
    mid = c.get("/api/markets").json()[0]["id"]
    assert c.post(f"/api/markets/{mid}/resolve").status_code == 403
    assert c.post(f"/api/markets/{mid}/resolve",
                  headers={"X-Presenter-Key": "s3creto"}).status_code == 200
    body = {"question": "¿Pregunta nueva?", "criteria": "SÍ si pasa."}
    assert c.post("/api/markets", json=body).status_code == 403
    # La audiencia sigue pudiendo operar sin clave.
    assert trade(c, mid, "aye", "YES", 10).status_code in (200, 400)


@pytest.mark.parametrize("seed_set", ["oraculo", "agregacion", "mixta"])
def test_every_seed_set_opens_at_even_odds(seed_set, monkeypatch):
    monkeypatch.setenv("SEED_SET", seed_set)
    c = app_with(with_seed=True)
    markets = c.get("/api/markets").json()
    assert len(markets) == 3
    assert all(m["prices"]["YES"] == 0.5 for m in markets)


def test_oracle_seed_set_has_one_unresolvable_question(monkeypatch):
    monkeypatch.setenv("SEED_SET", "oraculo")
    c = app_with(with_seed=True)
    assert sorted(m["kind"] for m in c.get("/api/markets").json()) == ["futuro", "presente", "presente"]
