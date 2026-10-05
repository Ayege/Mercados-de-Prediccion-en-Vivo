"""El caso de uso de la nube con reloj falso: el tiempo avanza cuando el test lo dice."""
import asyncio

import pytest

from app.adapters.topology.mock import MockTopologyGenerator
from app.application.cloud import MAX_CATCHUP, CloudService
from app.domain.cloud.simulation import Simulation
from app.domain.cloud.topology import Draft
from app.domain.errors import SimulationError


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def cloud(generator=None):
    clock = Clock()
    return CloudService(Simulation(), generator or MockTopologyGenerator(), 1.0, clock), clock


def test_paused_simulation_does_not_advance():
    c, clock = cloud()
    clock.now += 100
    assert c.view()["tick"] == 0


def test_running_simulation_advances_with_the_clock():
    c, clock = cloud()
    c.start()
    clock.now += 7.5
    assert c.view()["tick"] == 7
    clock.now += 0.5
    assert c.view()["tick"] == 8


def test_long_pause_catches_up_at_most_a_bounded_amount():
    c, clock = cloud()
    c.start()
    clock.now += 10_000
    assert c.view()["tick"] == MAX_CATCHUP
    clock.now += 1
    assert c.view()["tick"] == MAX_CATCHUP + 1


def test_step_is_bounded():
    c, _ = cloud()
    with pytest.raises(SimulationError):
        c.step(MAX_CATCHUP + 1)


class Broken:
    name = model = "roto"

    async def propose(self, brief):
        return Draft(None, "roto", ["respuesta no parseable → sin propuesta (fail-closed)"])


def test_broken_generator_is_recorded_as_rejected():
    c, _ = cloud(Broken())
    v = asyncio.run(c.propose("generativo"))
    assert v["proposals"][0]["accepted"] is False
    assert v["topology"]["replicas"] == {"us-east1": 4}


def test_generator_receives_the_constraints_but_the_policy_decides():
    seen = []

    class Liar:
        name = model = "mentiroso"

        async def propose(self, brief):
            seen.append(brief)
            return Draft({"replicas": {"us-east1": 6}}, "mentiroso", ["dice que cumple"])

    c, _ = cloud(Liar())
    v = asyncio.run(c.propose("generativo"))
    assert seen[0]["restricciones"]["min_regiones"] == 2
    assert v["proposals"][0]["accepted"] is False


def test_unknown_source_is_rejected():
    c, _ = cloud()
    with pytest.raises(SimulationError):
        asyncio.run(c.propose("oraculo"))
