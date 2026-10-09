"""La foto del estado: la sala sobrevive a que la API escale a cero, y nada ajeno se restaura."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.adapters.state import MemoryStateStore, SignedPickle
from app.application.persistence import Persistence
from app.config import Settings
from app.entrypoints.http.api import create_app
from app.main import build_cloud, build_infra, build_news, build_service

KEY = "k" * 32


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def room(store, clock, key=KEY, fingerprint=b"f" * 32):
    """Una instancia de la API, como la que Cloud Run arranca en frío."""
    settings = Settings(backend="mock", presenter_key=key, room_code="auto", oracle_cooldown=0,
                        infra_mode="ensayo")
    cloud = build_cloud(settings)
    infra = build_infra(settings, cloud)
    service = build_service(settings, cloud=cloud, infra=infra)
    news = build_news(settings, service)
    codec = SignedPickle(key, fingerprint=fingerprint)
    persistence = Persistence(store, codec, service.repo,
                              {"mercado": service, "noticias": news, "nube": cloud, "infra": infra},
                              every=5, clock=clock)
    app = create_app(service, cloud, infra, key, news=news, persistence=persistence)
    return app, service, persistence


def test_the_room_survives_scaling_to_zero():
    store, clock = MemoryStateStore(), Clock()
    app, service, _ = room(store, clock)
    with TestClient(app) as c:
        code = c.get("/api/sala", headers={"X-Presenter-Key": KEY}).json()["code"]
        mid = c.post("/api/markets", json={"question": "¿Llueve mañana en SDQ?", "criteria": "SÍ si llueve."},
                     headers={"X-Presenter-Key": KEY}).json()["id"]
        token = c.post("/api/entrar", json={"name": "aye", "code": code}).json()["token"]
        c.post(f"/api/markets/{mid}/trade", json={"user": "aye", "outcome": "YES", "amount": 100},
               headers={"X-User-Token": token})
    assert store.blob is not None  # el apagado guardó lo último

    app2, service2, _ = room(store, clock)
    assert service2.room_code != code  # recién arrancada, antes de restaurar, tendría otro código
    with TestClient(app2) as c:
        assert c.get("/api/sala", headers={"X-Presenter-Key": KEY}).json()["code"] == code
        me = c.get("/api/users/aye", headers={"X-User-Token": token})
        assert me.status_code == 200 and me.json()["balance"] == 900
        assert c.get(f"/api/markets/{mid}").json()["orders"] == 1


def test_saves_are_throttled_but_never_lost():
    store, clock = MemoryStateStore(), Clock()
    _, service, persistence = room(store, clock)
    for _ in range(10):
        persistence.touch()
        asyncio.run(persistence.maybe_save())
    assert store.saves == 1 and persistence.dirty
    clock.now += 5
    asyncio.run(persistence.maybe_save())
    assert store.saves == 2 and not persistence.dirty


@pytest.mark.parametrize("change", ["key", "code", "age", "tamper"])
def test_a_foreign_old_or_tampered_snapshot_starts_from_scratch(change):
    store, clock = MemoryStateStore(), Clock()
    _, service, persistence = room(store, clock)
    service.create("¿Pregunta de otra sesión?", "criterio")
    asyncio.run(persistence.save())
    kw = {}
    if change == "key":
        kw["key"] = "z" * 32
    elif change == "code":
        kw["fingerprint"] = b"g" * 32
    elif change == "age":
        clock.now += 13 * 3600
    else:
        store.blob = store.blob[:-1] + bytes([store.blob[-1] ^ 1])
    _, fresh, persistence2 = room(store, clock, **kw)
    assert asyncio.run(persistence2.restore()) is False
    assert all(m.question != "¿Pregunta de otra sesión?" for m in fresh.repo.markets())


def test_a_failed_save_is_retried():
    class Down(MemoryStateStore):
        async def save(self, blob):
            raise OSError("sin red")

    clock = Clock()
    _, _, persistence = room(Down(), clock)
    persistence.touch()
    assert asyncio.run(persistence.save()) is False and persistence.dirty


def test_the_snapshot_needs_a_strong_key():
    with pytest.raises(RuntimeError, match="ESTADO_BUCKET"):
        Settings(state_bucket="b", presenter_key="corta").check()
    with pytest.raises(ValueError):
        SignedPickle("corta")


def test_the_code_fingerprint_is_stable_and_round_trips():
    from app.adapters.state import code_fingerprint

    assert code_fingerprint() == code_fingerprint() and len(code_fingerprint()) == 32
    codec = SignedPickle(KEY)
    assert codec.loads(codec.dumps({"x": [1, 2]}, 10.0), 11.0) == {"x": [1, 2]}
