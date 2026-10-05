"""Casos de uso con dobles de los puertos: sin HTTP, sin red, con reloj controlado."""
import asyncio

import pytest

from app.adapters.memory import InMemoryRepository
from app.application.errors import Cooldown
from app.application.service import MarketService
from app.domain.errors import MarketError
from app.domain.verdict import Verdict


class FakeOracle:
    name = model = "fake"

    def __init__(self, outcome="UNRESOLVED"):
        self.outcome = outcome
        self.calls = []

    async def resolve(self, question, criteria, fault=None):
        self.calls.append((question, fault))
        return Verdict(self.outcome, 1.0, "", trace=["fake"])


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def service(oracle=None, clock=None, cooldown=30):
    return MarketService(InMemoryRepository(), oracle or FakeOracle(), oracle_cooldown=cooldown,
                         clock=clock or Clock())


def test_cooldown_follows_the_clock():
    clock = Clock()
    s = service(clock=clock)
    mid = s.create("¿Pregunta?", "Criterio")["id"]
    asyncio.run(s.resolve(mid))
    with pytest.raises(Cooldown):
        asyncio.run(s.resolve(mid))
    clock.now += 31
    asyncio.run(s.resolve(mid))


def test_census_market_never_calls_the_oracle():
    oracle = FakeOracle("YES")
    s = service(oracle)
    mid = s.create("¿Pregunta?", "Criterio", kind="sala")["id"]
    for name in "abcde":
        s.answer_census(mid, name, s.enter(name)["token"], True)
    assert asyncio.run(s.resolve(mid))["outcome"] == "YES"
    assert oracle.calls == []


def test_fault_is_forwarded_to_the_oracle_port():
    oracle = FakeOracle()
    s = service(oracle)
    mid = s.create("¿Pregunta?", "Criterio")["id"]
    asyncio.run(s.resolve(mid, "un_dominio"))
    assert oracle.calls == [("¿Pregunta?", "un_dominio")]


def test_unknown_fault_is_rejected_before_calling_the_oracle():
    oracle = FakeOracle()
    s = service(oracle)
    mid = s.create("¿Pregunta?", "Criterio")["id"]
    with pytest.raises(MarketError):
        asyncio.run(s.resolve(mid, "meteorito"))
    assert oracle.calls == []


def test_failed_trade_does_not_charge_the_account():
    s = service()
    mid = s.create("¿Pregunta?", "Criterio")["id"]
    aye = s.enter("aye")["token"]
    with pytest.raises(MarketError):
        s.trade(mid, "aye", aye, "MAYBE", 100)
    assert s.account("aye", aye)["balance"] == 1000


def test_settlement_pays_every_holder():
    s = service(FakeOracle("NO"))
    mid = s.create("¿Pregunta?", "Criterio")["id"]
    aye, bob = s.enter("aye")["token"], s.enter("bob")["token"]
    yes = s.trade(mid, "aye", aye, "YES", 100)["shares"]
    no = s.trade(mid, "bob", bob, "NO", 100)["shares"]
    asyncio.run(s.resolve(mid))
    assert s.account("aye", aye)["balance"] == pytest.approx(900)
    assert s.account("bob", bob)["balance"] == pytest.approx(900 + no)
    assert yes > 0
