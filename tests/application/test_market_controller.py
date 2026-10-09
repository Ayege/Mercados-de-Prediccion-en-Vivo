"""El mercado real dentro del controlador de infraestructura, contra la nube de ensayo."""
import asyncio

from app.adapters.infra.fake import FakeNodeGateway
from app.adapters.prices import FixedPrices
from app.application.infra import InfraController
from app.application.real_market import RealMarket
from app.domain.cloud.real_market import MarketBudget


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def setup(budget=None):
    clock, gw = Clock(), FakeNodeGateway()
    market = RealMarket(gw, FixedPrices(), budget, clock=clock)
    c = InfraController(gw, lambda: {"us-east1": 1, "us-central1": 1}, "ensayo", clock=clock, market=market)
    return c, market, gw, clock


def run(c, clock, cycles, rps=15):
    async def go():
        for _ in range(cycles):
            for _ in range(rps * 10):
                c.count_request()
            clock.now += 10
            await c.cycle()

    asyncio.run(go())


def test_paused_market_creates_nothing():
    c, market, gw, clock = setup()
    run(c, clock, 3)
    assert gw.agents == {} and market.cycles == 0


def test_active_market_creates_agents_trades_and_spends_real_money():
    c, market, gw, clock = setup()
    c.set_active(True)
    run(c, clock, 8)
    assert len(gw.agents) == 4
    assert market.trades and sum(market.trades[-1].fills.values()) == 12  # el tope, no los 150 pedidos
    assert market.spend > 0


def test_contracts_and_generations_happen():
    c, market, _, clock = setup(MarketBudget(contract_every=2, generation_cycles=4))
    c.set_active(True)
    run(c, clock, 14)
    assert market.contracts and market.generations


def test_warm_budget_holds_in_real_services():
    c, market, gw, clock = setup(MarketBudget(max_warm=1, generation_cycles=3))
    c.set_active(True)
    run(c, clock, 20)
    assert sum(a.warm for a in gw.agents.values()) <= 1


def test_shutdown_and_vigil_delete_agents_too():
    c, market, gw, clock = setup()
    c.set_active(True)
    run(c, clock, 4)
    asyncio.run(c.shutdown())
    assert gw.agents == {}
    c.set_active(True)
    run(c, clock, 4)
    c.touch()
    clock.now += c.ttl + 1
    assert asyncio.run(c.vigil())["apagado"] is True and gw.agents == {}


def test_public_view_hides_market_errors():
    c, market, _, _ = setup()
    market.error = "403: permission denied on projects/x"
    assert "projects/x" not in str(c.view(detailed=False)["market"])


def test_real_cooperation_is_judged_only_when_generation_3_closes():
    c, market, gw, clock = setup(MarketBudget(generation_cycles=2))
    assert c.judge("cooperacion_real").outcome == "UNRESOLVED"
    c.set_active(True)
    run(c, clock, 3)  # el primer ciclo solo crea los servicios
    assert market.generation < 3 and c.judge("cooperacion_real").outcome == "UNRESOLVED"
    for _ in range(20):
        if market.generation > 3:
            break
        run(c, clock, 1)
    verdict = c.judge("cooperacion_real")
    assert verdict.outcome in ("YES", "NO") and verdict.model == "mercado real"
    assert "generación 3" in verdict.reasoning
