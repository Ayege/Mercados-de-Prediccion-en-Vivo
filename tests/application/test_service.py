"""Casos de uso con dobles de los puertos: sin HTTP, sin red, con reloj controlado."""
import asyncio

import pytest

from app.adapters.memory import InMemoryRepository
from app.application.errors import Cooldown
from app.application.service import MarketService
from app.domain.errors import MarketError
from app.domain.framing import Framing, Headline
from app.domain.verdict import Verdict


class FakeOracle:
    name = model = "fake"

    def __init__(self, outcome="UNRESOLVED"):
        self.outcome = outcome
        self.calls = []

    async def resolve(self, question, criteria, fault=None, news=None):
        self.calls.append((question, fault) if news is None else (question, fault, news))
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


# --- encuadre -----------------------------------------------------------------

FRAMING = Framing(Headline("Todo va según el calendario", "titular de ensayo"),
                  Headline("Advierten que la fecha puede moverse", "titular de ensayo"))


class GullibleOracle(FakeOracle):
    """Responde hacia donde empuja el titular que lee."""

    async def resolve(self, question, criteria, fault=None, news=None):
        self.calls.append((question, fault, news))
        return Verdict(news.lean if news else self.outcome, 0.9, "", trace=["fake"])


def test_framed_question_is_checked_against_both_headlines():
    oracle = FakeOracle("YES")
    s = service(oracle)
    mid = s.create("¿Pregunta?", "Criterio", framing=FRAMING)["id"]
    v = asyncio.run(s.resolve(mid))
    assert v["outcome"] == "YES" and len(oracle.calls) == 3
    assert set(v["oracle"]["framing"]) == {"neutral", "pro_si", "pro_no"}


def test_headline_dependent_verdict_stays_unresolved():
    s = service(GullibleOracle("YES"))
    mid = s.create("¿Pregunta?", "Criterio", framing=FRAMING)["id"]
    v = asyncio.run(s.resolve(mid))
    assert v["status"] == "open" and v["oracle"]["outcome"] == "UNRESOLVED"


def test_undecided_neutral_read_skips_the_framed_reads():
    oracle = FakeOracle("UNRESOLVED")
    s = service(oracle)
    mid = s.create("¿Pregunta?", "Criterio", framing=FRAMING)["id"]
    asyncio.run(s.resolve(mid))
    assert len(oracle.calls) == 1


def test_trusted_news_fault_reaches_the_oracle_as_trusted_news():
    oracle = GullibleOracle("YES")
    s = service(oracle)
    mid = s.create("¿Pregunta?", "Criterio", framing=FRAMING)["id"]
    asyncio.run(s.resolve(mid, "noticia_como_verdad"))
    neutral, *framed = oracle.calls
    assert neutral[1] is None and neutral[2] is None
    assert all(c[2].trusted for c in framed)


def test_trusted_news_fault_needs_headlines():
    oracle = FakeOracle()
    s = service(oracle)
    mid = s.create("¿Pregunta?", "Criterio")["id"]
    with pytest.raises(MarketError):
        asyncio.run(s.resolve(mid, "noticia_como_verdad"))
    assert oracle.calls == []


def test_each_person_sees_one_headline_and_the_room_sees_none_until_revealed():
    s = service()
    mid = s.create("¿Pregunta?", "Criterio", framing=FRAMING)["id"]
    seen = {s.account(n, s.enter(n)["token"])["headlines"][mid]["text"] for n in ("aye", "bob")}
    assert seen == {FRAMING.pro_si.text, FRAMING.pro_no.text}
    assert s.view(mid)["framing"]["headlines"] is None
    assert s.view(mid)["framing"]["groups"]["pro_si"]["exposed"] == 1
    assert s.reveal(mid)["framing"]["headlines"]["pro_no"]["text"] == FRAMING.pro_no.text


def test_resolution_reveals_the_headlines():
    s = service(FakeOracle("NO"))
    mid = s.create("¿Pregunta?", "Criterio", framing=FRAMING)["id"]
    assert asyncio.run(s.resolve(mid))["framing"]["revealed"] is True


def test_reveal_needs_headlines():
    s = service()
    mid = s.create("¿Pregunta?", "Criterio")["id"]
    with pytest.raises(MarketError):
        s.reveal(mid)
