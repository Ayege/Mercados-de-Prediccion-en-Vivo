import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.market import Engine
from app.oracle import MockOracle


@pytest.fixture()
def client():
    return TestClient(create_app(Engine(MockOracle(), oracle_cooldown=0), with_seed=False))


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
    c = TestClient(create_app(Engine(MockOracle(), oracle_cooldown=60), with_seed=False))
    mid = new_market(c)
    assert c.post(f"/api/markets/{mid}/resolve").status_code == 200
    assert c.post(f"/api/markets/{mid}/resolve").status_code == 429


def test_unknown_market_is_404(client):
    assert client.get("/api/markets/nope").status_code == 404


def test_seeded_app_serves_markets_and_health():
    c = TestClient(create_app(Engine(MockOracle())))
    assert len(c.get("/api/markets").json()) == 3
    assert c.get("/healthz").json() == {"ok": True}
