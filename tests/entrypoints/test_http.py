import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build, build_cloud, build_infra, build_service


def app_with(with_seed=False, **overrides):
    settings = Settings.from_env()
    settings = Settings(**{**settings.__dict__, "oracle_cooldown": 0, "backend": "mock", **overrides})
    cloud = build_cloud(settings)
    infra = build_infra(settings, cloud)
    service = build_service(settings, cloud=cloud, infra=infra)
    return TestClient(build(settings, service, cloud, infra, with_seed=with_seed))


@pytest.fixture()
def client():
    return app_with()


def new_market(client):
    r = client.post(
        "/api/markets", json={"question": "¿Llueve mañana en SDQ?", "criteria": "SÍ si llueve."}
    )
    assert r.status_code == 201
    return r.json()["id"]


def token(client, user):
    """Entra una vez por nombre y guarda el token, como hace el navegador."""
    tokens = client.__dict__.setdefault("tokens", {})
    if user.lower() not in tokens:
        r = client.post("/api/entrar", json={"name": user})
        assert r.status_code == 201, r.text
        tokens[user.lower()] = r.json()["token"]
    return tokens[user.lower()]


def trade(client, mid, user, outcome, amount):
    return client.post(f"/api/markets/{mid}/trade", json={"user": user, "outcome": outcome, "amount": amount},
                       headers={"X-User-Token": token(client, user)})


def census(client, mid, user, answer):
    return client.post(f"/api/markets/{mid}/census", json={"user": user, "answer": answer},
                       headers={"X-User-Token": token(client, user)})


def balance(client, user):
    return client.get(f"/api/users/{user}", headers={"X-User-Token": token(client, user)}).json()["balance"]


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
    assert balance(client, "aye") == pytest.approx(900 + shares)
    assert balance(client, "bob") == pytest.approx(900)


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
        assert census(client, mid, f"u{i}", answer).status_code == 200
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["status"] == "resolved" and m["outcome"] == "YES"
    assert m["oracle"]["model"] == "censo"


def test_census_below_minimum_stays_open(client):
    mid = sala_market(client)
    census(client, mid, "aye", True)
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["status"] == "open" and m["oracle"]["outcome"] == "UNRESOLVED"


def test_census_is_one_answer_per_person(client):
    mid = sala_market(client)
    census(client, mid, "aye", True)
    r = census(client, mid, "AYE", False)
    assert r.status_code == 400


def test_census_rejected_on_oracle_market(client):
    mid = new_market(client)
    r = census(client, mid, "aye", True)
    assert r.status_code == 400


def test_census_answers_are_not_exposed(client):
    mid = sala_market(client)
    census(client, mid, "aye", True)
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


# --- nube simulada ---------------------------------------------------------------


def test_cloud_view_is_public_and_controls_are_guarded(monkeypatch):
    monkeypatch.setenv("PRESENTER_KEY", "k")
    c = app_with()
    assert c.get("/api/nube").json()["tick"] == 0
    assert c.post("/api/nube/avanzar", params={"n": 5}).status_code == 403
    assert c.post("/api/nube/fallas", json={"kind": "caida_nodo"}).status_code == 403
    assert c.post("/api/nube/topologias", params={"fuente": "evolutivo"}).status_code == 403
    v = c.post("/api/nube/avanzar", params={"n": 5}, headers={"X-Presenter-Key": "k"}).json()
    assert v["tick"] == 5


def test_cloud_rejects_unknown_fault_and_source(client):
    assert client.post("/api/nube/fallas", json={"kind": "meteorito"}).status_code == 422
    assert client.post("/api/nube/topologias", params={"fuente": "x"}).status_code == 422


def test_simulation_market_needs_a_known_predicate(client):
    body = {"question": "¿Pregunta de la nube?", "criteria": "La resuelve la simulación.",
            "kind": "simulacion"}
    assert client.post("/api/markets", json=body).status_code == 400
    assert client.post("/api/markets", json=body | {"predicate": "inventado"}).status_code == 400
    assert client.post("/api/markets", json=body | {"predicate": "topologia_llm"}).status_code == 201


def test_simulation_market_resolves_from_the_simulation(client):
    body = {"question": "¿Pasará la topología?", "criteria": "La resuelve la simulación.",
            "kind": "simulacion", "predicate": "topologia_llm"}
    mid = client.post("/api/markets", json=body).json()["id"]
    first = client.post(f"/api/markets/{mid}/resolve").json()
    assert first["status"] == "open" and first["oracle"]["model"] == "simulación"
    client.post("/api/nube/topologias", params={"fuente": "generativo"})  # el simulado acierta primero
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["status"] == "resolved" and m["outcome"] == "YES"


def test_nube_seed_set_is_all_simulation_markets(monkeypatch):
    monkeypatch.setenv("SEED_SET", "nube")
    c = app_with(with_seed=True)
    assert {m["kind"] for m in c.get("/api/markets").json()} == {"simulacion"}


# --- infraestructura real --------------------------------------------------------


def test_infra_is_off_by_default(client):
    assert client.get("/api/infra").json() == {"mode": "apagado"}
    assert client.post("/api/infra/actuar", params={"activo": True}).status_code == 409


def test_rehearsal_infra_is_guarded_and_counts_demand(monkeypatch):
    monkeypatch.setenv("INFRA_MODE", "ensayo")
    monkeypatch.setenv("PRESENTER_KEY", "k")
    c = app_with()
    assert c.get("/api/infra").json()["mode"] == "ensayo"
    for path in ("/api/infra/ciclo", "/api/infra/apagar"):
        assert c.post(path).status_code == 403
    assert c.post("/api/infra/actuar", params={"activo": True}).status_code == 403
    c.get("/api/markets")
    v = c.post("/api/infra/ciclo", headers={"X-Presenter-Key": "k"}).json()
    assert v["rps"][-1]["real"] > 0


def test_real_mode_refuses_to_start_without_its_settings(monkeypatch):
    monkeypatch.setenv("INFRA_MODE", "real")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")
    with pytest.raises(RuntimeError, match="NODO_IMAGEN"):
        app_with()


def test_real_predicate_is_unresolved_when_infra_is_off(client):
    body = {"question": "¿Se reparará el nodo real?", "criteria": "Lo resuelve la infraestructura.",
            "kind": "simulacion", "predicate": "autorreparacion_real"}
    mid = client.post("/api/markets", json=body).json()["id"]
    m = client.post(f"/api/markets/{mid}/resolve").json()
    assert m["status"] == "open" and "apagada" in m["oracle"]["trace"][-1]


def test_vigil_is_guarded(monkeypatch):
    monkeypatch.setenv("INFRA_MODE", "ensayo")
    monkeypatch.setenv("PRESENTER_KEY", "k")
    c = app_with()
    assert c.post("/api/infra/vigilia").status_code == 403
    assert c.post("/api/infra/vigilia", headers={"X-Presenter-Key": "k"}).json()["apagado"] is False


def test_info_and_markets_say_who_resolves(monkeypatch):
    monkeypatch.setenv("INFRA_MODE", "ensayo")
    monkeypatch.setenv("SEED_SET", "nube_real")
    c = app_with(with_seed=True)
    assert c.get("/api/info").json()["infra"] == "ensayo"
    resolvers = {m["predicate"]: m["resolver"] for m in c.get("/api/markets").json()}
    assert resolvers["autorreparacion_real"] == "infraestructura real"
    assert resolvers["cooperacion_g5"] == "simulación"


# --- encuadre -------------------------------------------------------------------

FRAMED = {"question": "¿Llueve mañana en SDQ?", "criteria": "SÍ si llueve.",
          "framing": {"pro_si": {"text": "Alerta: se acercan lluvias fuertes", "source": "titular de ensayo"},
                      "pro_no": {"text": "Se espera un fin de semana seco", "source": "titular de ensayo"}}}


def test_framed_market_hides_headlines_from_the_projection_until_revealed(client):
    mid = client.post("/api/markets", json=FRAMED).json()["id"]
    h = client.get("/api/users/aye", headers={"X-User-Token": token(client, "aye")}).json()["headlines"][mid]
    assert h["text"] in ("Alerta: se acercan lluvias fuertes", "Se espera un fin de semana seco")
    public = client.get(f"/api/markets/{mid}").json()["framing"]
    assert public["headlines"] is None and "aye" not in str(public)
    assert client.post(f"/api/markets/{mid}/revelar").json()["framing"]["headlines"]["pro_si"]


def test_headline_link_must_be_https(client):
    body = {**FRAMED, "framing": {**FRAMED["framing"], "pro_si": {
        "text": "Alerta: se acercan lluvias fuertes", "source": "medio", "url": "javascript:alert(1)"}}}
    assert client.post("/api/markets", json=body).status_code == 422


def test_reveal_is_presenter_only(monkeypatch):
    monkeypatch.setenv("PRESENTER_KEY", "s3creto")
    monkeypatch.setenv("SEED_SET", "encuadre")
    c = app_with(with_seed=True)
    mid = next(m["id"] for m in c.get("/api/markets").json() if m["framing"])
    assert c.post(f"/api/markets/{mid}/revelar").status_code == 403


def test_trusted_news_fault_is_accepted_only_on_framed_markets(client, monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "YES")
    plain = new_market(client)
    assert client.post(f"/api/markets/{plain}/resolve?fault=noticia_como_verdad").status_code == 400
    framed = client.post("/api/markets", json=FRAMED).json()["id"]
    r = client.post(f"/api/markets/{framed}/resolve?fault=noticia_como_verdad").json()
    assert r["status"] == "open" and r["oracle"]["outcome"] == "UNRESOLVED"
    r = client.post(f"/api/markets/{framed}/resolve").json()
    assert r["outcome"] == "YES" and r["oracle"]["framing"]["pro_no"]["outcome"] == "YES"


def test_framing_seed_set_has_two_framed_questions_and_a_control(monkeypatch):
    monkeypatch.setenv("SEED_SET", "encuadre")
    markets = app_with(with_seed=True).get("/api/markets").json()
    assert [bool(m["framing"]) for m in markets] == [True, True, False]
    assert all(m["prices"]["YES"] == 0.5 for m in markets)


def test_seed_sets_combine_with_plus(monkeypatch):
    monkeypatch.setenv("SEED_SET", "encuadre+nube")
    assert len(app_with(with_seed=True).get("/api/markets").json()) == 7


def test_unknown_seed_set_is_rejected(monkeypatch):
    monkeypatch.setenv("SEED_SET", "encuadre+meteorito")
    with pytest.raises(ValueError, match="meteorito"):
        app_with(with_seed=True)
