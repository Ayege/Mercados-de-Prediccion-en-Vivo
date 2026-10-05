import pytest

from app.domain.cloud.simulation import GEN_TICKS, Simulation
from app.domain.errors import SimulationError


def run(sim, ticks):
    for _ in range(ticks):
        sim.tick()
    return sim


def test_same_seed_same_world():
    a, b = run(Simulation(seed=3), 60), run(Simulation(seed=3), 60)
    assert a.series.demand == b.series.demand
    assert [x.genome for x in a.agents] == [x.genome for x in b.agents]


def test_different_seed_different_world():
    assert run(Simulation(seed=3), 30).series.demand != run(Simulation(seed=4), 30).series.demand


def test_generation_closes_every_cycle():
    sim = run(Simulation(), GEN_TICKS * 2)
    assert [g.number for g in sim.generations] == [1, 2]


def test_node_failure_is_detected_and_eventually_repaired():
    sim = run(Simulation(seed=2), 30)
    fault = sim.inject("caida_nodo")
    run(sim, 40)
    incident = next(i for i in sim.incidents if i.fault == fault.id)
    assert incident.tick == fault.tick  # 400 ms contra ~30: se ve en el mismo tick
    assert fault.cleared is not None and fault.cleared > fault.tick


def test_demand_spike_triggers_emergency_autoscaling():
    sim = run(Simulation(seed=2), 60)
    fault = sim.inject("pico_demanda")
    run(sim, 10)
    assert any(i.fault == fault.id and "emergencia" in i.action for i in sim.incidents)


def test_cannot_break_a_node_that_is_already_broken():
    sim = run(Simulation(), 20)
    f = sim.inject("caida_nodo")
    with pytest.raises(SimulationError):
        sim.inject("latencia", f.target)


def test_unknown_fault_and_predicate_are_rejected():
    sim = Simulation()
    with pytest.raises(SimulationError):
        sim.inject("meteorito")
    with pytest.raises(SimulationError):
        sim.judge("el_futuro")


def test_predicates_stay_unresolved_until_decidable():
    sim = run(Simulation(seed=2), 30)
    assert {sim.judge(p).outcome for p in ("cooperacion_g5", "autorreparacion", "topologia_llm")} == {
        "UNRESOLVED"}
    run(sim, GEN_TICKS * 5)
    assert sim.judge("cooperacion_g5").outcome in ("YES", "NO")


def test_llm_predicate_judges_the_first_generative_proposal_only():
    sim = Simulation()
    sim.review("generativo", "m", {"replicas": {"us-east1": 5}}, [])
    sim.review("generativo", "m", {"replicas": {"us-east1": 2, "us-central1": 2}}, [])
    assert sim.judge("topologia_llm").outcome == "NO"


def test_rejected_proposal_never_replaces_the_topology():
    sim = Simulation()
    before = dict(sim.topology)
    record = sim.review("generativo", "m", {"replicas": {"marte-central1": 4}}, [])
    assert not record.adopted and sim.topology == before


def test_accepted_better_proposal_is_adopted():
    sim = Simulation()
    record = sim.review("generativo", "m", {"replicas": {"us-east1": 2, "us-central1": 2}}, [])
    assert record.adopted and sim.topology == {"us-east1": 2, "us-central1": 2}
