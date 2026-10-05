"""El mercado real sin red: costos, liquidación y evolución con precios de la foto del catálogo."""
import random

import pytest

from app.adapters.prices import SNAPSHOT
from app.domain.cloud.real_market import (
    MarketBudget,
    RealAgent,
    RealGenome,
    WorkResult,
    auction,
    evolve,
    settle,
)

BUDGET = MarketBudget()


def agent(agent_id, region="us-east1", markup=0.5, warm=False):
    return RealAgent(agent_id, region, RealGenome(markup, 0.5, warm))


def test_request_cost_rounds_up_to_100_ms():
    one = SNAPSHOT.request_cost("us-east1", 5)
    assert one == pytest.approx(SNAPSHOT.request_cost("us-east1", 99))
    assert SNAPSHOT.request_cost("us-east1", 101) > one


def test_tier_2_regions_cost_more():
    assert SNAPSHOT.request_cost("southamerica-east1", 5) > SNAPSHOT.request_cost("us-east1", 5)
    assert SNAPSHOT.idle_cost("southamerica-east1", 3600) > SNAPSHOT.idle_cost("us-east1", 3600)


def test_an_hour_warm_costs_under_a_cent():
    assert SNAPSHOT.idle_cost("us-east1", 3600) == pytest.approx(0.0045)


def test_auction_never_sells_more_than_the_cost_cap():
    agents = [agent(f"r{i}") for i in range(4)]
    c = auction(agents, SNAPSHOT, BUDGET, demand=500)
    assert sum(c.fills.values()) <= BUDGET.max_requests


def test_cheaper_agent_sells_first():
    cheap, dear = agent("r1", markup=0.1), agent("r2", markup=1.5)
    c = auction([cheap, dear], SNAPSHOT, BUDGET, demand=3)
    assert c.fills == {"r1": 3}


def test_only_on_time_answers_earn_but_every_request_costs():
    a = agent("r1")
    c = auction([a], SNAPSHOT, BUDGET, demand=3)
    results = {"r1": [WorkResult(50, 5, 200), WorkResult(1500, 5, 200), WorkResult(None, None, 503)]}
    settle([a], c, results, SNAPSHOT, BUDGET, cycle_seconds=10)
    assert (a.served, a.late, a.failed) == (1, 1, 1)
    assert a.revenue == pytest.approx(c.price)
    assert a.cost == pytest.approx(3 * SNAPSHOT.request_cost("us-east1", 5))


def test_warm_agents_pay_for_idle_time():
    cold, warm = agent("r1"), agent("r2", warm=True)
    c = auction([cold, warm], SNAPSHOT, BUDGET, demand=0)
    settle([cold, warm], c, {}, SNAPSHOT, BUDGET, cycle_seconds=10)
    assert cold.cost == 0 and warm.cost == pytest.approx(SNAPSHOT.idle_cost("us-east1", 10))


def test_evolution_respects_the_warm_budget_and_resets_the_books():
    rng = random.Random(1)
    agents = [agent(f"r{i}", warm=True) for i in range(4)]
    for i, a in enumerate(agents):
        a.revenue = float(i)
    evolve(agents, rng, generation=2, budget=MarketBudget(max_warm=1))
    assert sum(a.genome.warm for a in agents) <= 1
    assert all(a.revenue == 0 and a.cost == 0 for a in agents)


def test_topology_cost_ratios_are_the_real_price_ratios():
    from app.domain.cloud.catalog import REGIONS

    base = SNAPSHOT.idle_cost("us-east1", 1)
    for name, region in REGIONS.items():
        assert region.cost == pytest.approx(SNAPSHOT.idle_cost(name, 1) / base), name
