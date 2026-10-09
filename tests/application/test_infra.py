"""El controlador de infraestructura contra la nube de ensayo, con reloj falso."""
import asyncio

import pytest

from app.adapters.infra.fake import FakeNodeGateway
from app.application.infra import InfraController
from app.domain.errors import SimulationError


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def setup(topology=None):
    clock, gw = Clock(), FakeNodeGateway()
    topo = topology if topology is not None else {"us-east1": 2, "us-central1": 2}
    return InfraController(gw, lambda: topo, "ensayo", clock=clock), gw, clock, topo


def cycles(c, clock, n, rps=15.0):
    async def go():
        for _ in range(n):
            for _ in range(int(rps * 10)):
                c.count_request()
            clock.now += 10
            await c.cycle()
    asyncio.run(go())


def test_nothing_is_touched_until_the_presenter_activates():
    c, gw, clock, _ = setup()
    cycles(c, clock, 3)
    assert gw.calls == []
    assert all(not e["allowed"] for e in c.view()["log"])


def test_topology_becomes_real_nodes_scaled_by_demand():
    c, gw, clock, _ = setup()
    c.set_active(True)
    cycles(c, clock, 4, rps=15)
    nodes = {n["region"]: n for n in c.view()["nodes"]}
    assert set(nodes) == {"us-east1", "us-central1"}
    assert sum(n["min"] for n in nodes.values()) == 2  # 15 req/s / 10 por instancia


def test_view_shows_the_path_from_traffic_to_machines():
    c, _, clock, _ = setup()
    cycles(c, clock, 4, rps=45)
    s = c.view()["scaling"]
    assert s["rps_per_instance"] == 10.0 and s["forecast"] > 30
    assert s["wanted_min"] >= 4  # lo que pide la predicción
    assert s["allowed_min"] == 2  # lo que deja la política: 2 instancias mínimas en total


def test_no_demand_means_no_minimum_instances():
    c, _, clock, _ = setup()
    c.set_active(True)
    cycles(c, clock, 10, rps=0)
    assert all(n["min"] == 0 for n in c.view()["nodes"])


def test_real_fault_is_detected_repaired_and_judged():
    c, gw, clock, _ = setup()
    c.set_active(True)
    cycles(c, clock, 12)
    asyncio.run(c.inject("us-east1", "caida"))
    cycles(c, clock, 10)
    v = c.view()
    assert v["incidents"][0]["fault"] == 1 and v["faults"][0]["repaired"] is not None
    assert ("reparar", "us-east1") in gw.calls
    assert c.judge("autorreparacion_real").outcome in ("YES", "NO")


def test_fault_needs_active_actuation_and_a_warm_detector():
    c, _, clock, _ = setup()
    cycles(c, clock, 1)
    with pytest.raises(SimulationError):
        asyncio.run(c.inject("us-east1", "caida"))  # en pausa
    c.set_active(True)
    cycles(c, clock, 2)
    with pytest.raises(SimulationError):
        asyncio.run(c.inject("us-east1", "caida"))  # sin línea base todavía


def test_oversized_topology_is_clamped_not_applied_as_is():
    c, gw, clock, _ = setup({"us-east1": 9, "southamerica-east1": 9})
    c.set_active(True)
    cycles(c, clock, 3)
    assert all(n["max"] <= c.policy.max_max_per_region for n in c.view()["nodes"])
    assert any("recortado" in n for n in c.view()["notes"])


def test_shutdown_deletes_everything_and_pauses():
    c, gw, clock, _ = setup()
    c.set_active(True)
    cycles(c, clock, 3)
    asyncio.run(c.shutdown())
    cycles(c, clock, 2)
    assert c.view()["nodes"] == [] and c.active is False


def test_judge_waits_for_a_real_fault():
    c, *_ = setup()
    assert c.judge("autorreparacion_real").outcome == "UNRESOLVED"


def test_cycle_runs_only_when_due():
    c, gw, clock, _ = setup()
    asyncio.run(c.maybe_cycle())
    first = c.state.last_cycle
    clock.now += c.interval / 2
    asyncio.run(c.maybe_cycle())
    assert c.state.last_cycle == first
    clock.now += c.interval
    asyncio.run(c.maybe_cycle())
    assert c.state.last_cycle > first


def test_vigil_keeps_nodes_while_someone_watches():
    c, gw, clock, _ = setup()
    c.set_active(True)
    cycles(c, clock, 3)
    c.touch()
    clock.now += c.ttl - 1
    assert asyncio.run(c.vigil())["apagado"] is False
    assert gw.nodes


def test_vigil_deletes_forgotten_nodes():
    c, gw, clock, _ = setup()
    c.set_active(True)
    cycles(c, clock, 3)
    c.touch()
    clock.now += c.ttl + 1
    out = asyncio.run(c.vigil())
    assert out["apagado"] is True and gw.nodes == {} and c.active is False


def test_fresh_process_assumes_nobody_is_watching():
    c, gw, clock, _ = setup()
    c.set_active(True)
    cycles(c, clock, 3)  # los ciclos no cuentan como "alguien mira": eso lo hace touch()
    restarted = InfraController(gw, lambda: {}, "ensayo", clock=clock)
    assert asyncio.run(restarted.vigil())["apagado"] is True and gw.nodes == {}
