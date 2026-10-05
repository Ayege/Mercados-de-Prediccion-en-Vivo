"""Cada técnica de la nube simulada, probada por separado y sin la simulación."""
import random
from math import sin, tau

import pytest

from app.domain.cloud.agents import GENES, Agent, Genome
from app.domain.cloud.anomaly import Detector
from app.domain.cloud.auction import Ask, clear
from app.domain.cloud.coalitions import Contract, Member, form, shapley, value
from app.domain.cloud.evolution import next_generation, replicator
from app.domain.cloud.forecast import HoltWinters
from app.domain.cloud.topology import TopologyPolicy, evaluate, evolve

# --- predicción ---------------------------------------------------------------------


def test_holt_winters_beats_seasonal_naive_when_there_is_trend():
    hw, series, err_hw, err_naive = HoltWinters(), [], 0.0, 0.0
    for t in range(24 * 8):
        y = 100 + 0.5 * t + 30 * sin(tau * t / 24)
        if t >= 24 * 4:
            err_hw += abs(hw.forecast() - y)
            err_naive += abs(series[-24] - y)
        hw.update(y)
        series.append(y)
    assert err_hw < err_naive


def test_forecast_before_one_cycle_repeats_last_value():
    hw = HoltWinters()
    hw.update(42.0)
    assert hw.forecast() == 42.0


# --- subasta ------------------------------------------------------------------------


def test_auction_fills_cheapest_first_at_uniform_price():
    c = clear([Ask("caro", 3.0, 10), Ask("barato", 1.0, 5), Ask("medio", 2.0, 5)], 8, 10)
    assert c.fills == {"barato": 5, "medio": 3}
    assert c.price == 2.0 and c.unmet == 0


def test_auction_respects_reservation_price():
    c = clear([Ask("a", 1.0, 2), Ask("b", 5.0, 10)], 8, 2.0)
    assert c.fills == {"a": 2} and c.unmet == pytest.approx(6)


# --- coaliciones --------------------------------------------------------------------

M = [Member("a", "us-east1", 6, 1.0), Member("b", "us-central1", 6, 1.1), Member("c", "europe-west1", 6, 1.2)]
CONTRACT = Contract(qty=10, payment=20)


def test_contract_needs_two_regions():
    same = [Member("a", "us-east1", 20, 1.0), Member("b", "us-east1", 20, 1.0)]
    assert value(same, CONTRACT) == 0 and form(CONTRACT, same) is None


def test_shapley_is_efficient_and_rewards_contribution():
    c = form(CONTRACT, M)
    assert c is not None
    assert sum(c.shares.values()) == pytest.approx(c.value)
    assert all(s >= 0 for s in c.shares.values())


def test_shapley_symmetric_players_split_evenly_and_dummy_gets_zero():
    v = {frozenset(): 0, frozenset("x"): 0, frozenset("y"): 0, frozenset("z"): 0,
         frozenset("xy"): 10, frozenset("xz"): 0, frozenset("yz"): 0, frozenset("xyz"): 10}
    phi = shapley(["x", "y", "z"], lambda s: v[frozenset(s)])
    assert phi["x"] == pytest.approx(5) and phi["y"] == pytest.approx(5) and phi["z"] == pytest.approx(0)


# --- anomalías ----------------------------------------------------------------------


def test_detector_quiet_on_stationary_noise():
    rng, d = random.Random(1), Detector(min_jump=60)
    assert all(d.observe(20 + rng.gauss(0, 3)) is None for _ in range(500))


def test_detector_fires_on_spike_and_keeps_baseline_clean():
    rng, d = random.Random(1), Detector(min_jump=60)
    for _ in range(50):
        d.observe(20 + rng.gauss(0, 3))
    before = d.mean
    assert d.observe(400) is not None
    assert d.mean == before


# --- agentes y evolución ------------------------------------------------------------


def test_mutation_stays_within_gene_bounds():
    rng, g = random.Random(3), Genome(1.5, 0.5, 1.0, 0.0)
    for _ in range(200):
        g = g.mutate(rng, 0.5)
        for gene, (lo, hi) in GENES.items():
            assert lo <= getattr(g, gene) <= hi


def test_next_generation_keeps_the_elite_and_resets_fitness():
    rng = random.Random(5)
    agents = [Agent(f"a{i}", "us-east1", {"cpu": 1, "almacenamiento": 1, "ancho_banda": 1},
                    Genome.random(rng), fitness=float(i)) for i in range(8)]
    best = agents[-1].genome
    next_generation(agents, rng, generation=2)
    assert agents[-1].genome == best and agents[-1].born == 0
    assert all(a.fitness == 0 for a in agents)
    assert sum(a.born == 2 for a in agents) == 6


def test_replicator_grows_the_fitter_strategy_and_ignores_the_zero():
    share = {"cooperativo": 0.5, "agresivo": 0.5, "previsor": 0.0, "austero": 0.0}
    fit = {"cooperativo": 10.0, "agresivo": 5.0, "previsor": None, "austero": None}
    shifted = {k: (v - 1000 if v is not None else None) for k, v in fit.items()}
    p = replicator(share, fit)
    assert p["cooperativo"] > 0.5 and sum(p.values()) == pytest.approx(1)
    assert replicator(share, shifted) == pytest.approx(p)


# --- topologías ---------------------------------------------------------------------

POLICY = TopologyPolicy()


@pytest.mark.parametrize("raw,reason", [
    ({"replicas": {"us-east1": 5}}, "región(es)"),
    ({"replicas": {"us-east1": 2, "marte-central1": 2}}, "región inexistente"),
    ({"replicas": {"us-east1": 6, "southamerica-east1": 6, "europe-west1": 6}}, "presupuesto"),
    ({"replicas": {"us-east1": 2.5, "us-central1": 2}}, "no enteras"),
    ({"replicas": {"us-east1": True, "us-central1": 3}}, "no enteras"),
    ("todo en una región", "forma inválida"),
    (None, "forma inválida"),
])
def test_policy_rejects_with_the_reason(raw, reason):
    d = POLICY.check(raw)
    assert not d.accepted
    assert any(reason in line for line in d.trace)


def test_policy_accepts_a_sound_topology():
    assert POLICY.check({"replicas": {"us-east1": 2, "us-central1": 2}}).accepted


def test_evolutionary_search_finds_a_compliant_topology_better_than_legacy():
    replicas, curve = evolve(POLICY, random.Random(7))
    assert POLICY.check({"replicas": replicas}).accepted
    assert evaluate(replicas).value > evaluate({"us-east1": 4}).value
    assert curve == sorted(curve)  # con élite, el mejor nunca empeora
