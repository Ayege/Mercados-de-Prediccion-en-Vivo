"""En producción nada es simulado: oráculo, noticias, infraestructura y preguntas son reales."""
import asyncio

import pytest

from app.adapters.memory import InMemoryRepository
from app.adapters.oracle.mock import MockOracle
from app.adapters.topology.mock import MockTopologyGenerator
from app.application.cloud import CloudService
from app.application.judges import CompositeJudge
from app.application.service import MarketService
from app.config import Settings
from app.domain.cloud.simulation import Simulation
from app.domain.errors import MarketError, SimulationError
from app.domain.framing import Framing, Headline
from app.domain.verdict import AcceptancePolicy
from app.seeds import seed

KEY = "k" * 32
REAL = {"production": True, "presenter_key": KEY, "project": "p", "backend": "vertex", "infra_mode": "real"}


def settings(**over) -> Settings:
    return Settings(**{**Settings().__dict__, **REAL, **over})


def test_production_starts_only_when_everything_is_real():
    settings().check()


@pytest.mark.parametrize("over", [{"backend": "mock"}, {"project": ""}])
def test_production_refuses_a_simulated_oracle_or_newsroom(over):
    with pytest.raises(RuntimeError, match="ORACLE_BACKEND=vertex"):
        settings(**over).check()


@pytest.mark.parametrize("mode", ["apagado", "ensayo", "plan"])
def test_production_refuses_infrastructure_that_is_not_real(mode):
    with pytest.raises(RuntimeError, match="INFRA_MODE"):
        settings(infra_mode=mode).check()


def real_service() -> MarketService:
    cloud = CloudService(Simulation(), MockTopologyGenerator(), lab=False)
    return MarketService(InMemoryRepository(), MockOracle(AcceptancePolicy(0.8, 2)),
                         judge=CompositeJudge(cloud, None), only_real=True)


def test_questions_resolved_by_the_simulation_are_refused():
    with pytest.raises(MarketError, match="laboratorio simulado"):
        real_service().create("¿Coopera la generación 5?", "criterio", kind="simulacion",
                              predicate="cooperacion_g5")


def test_headlines_without_a_published_link_are_refused():
    rehearsal = Framing(Headline("Un titular escrito para ensayar", "titular de ensayo"),
                        Headline("Otro titular escrito para ensayar", "titular de ensayo"))
    with pytest.raises(MarketError, match="enlace https"):
        real_service().create("¿Pasó algo verificable?", "criterio", framing=rehearsal)
    published = Framing(Headline("Un titular que publicó un medio", "Medio A", "https://a.example/1"),
                        Headline("Otro titular que publicó otro medio", "Medio B", "https://b.example/2"))
    real_service().create("¿Pasó algo verificable?", "criterio", framing=published)


def test_the_real_seed_set_is_the_only_one_production_accepts():
    seed(real_service(), "real")
    for name in ("encuadre", "nube", "nube_real"):
        with pytest.raises(MarketError):
            seed(real_service(), name)


def test_without_the_lab_only_real_topology_proposals_remain():
    cloud = CloudService(Simulation(), MockTopologyGenerator(), lab=False)
    assert cloud.view()["lab"] is False
    for action in (cloud.start, cloud.pause, lambda: cloud.step(1), lambda: cloud.inject("caida_nodo"),
                   lambda: cloud.judge("cooperacion_g5")):
        with pytest.raises(SimulationError, match="laboratorio simulado está apagado"):
            action()
    view = asyncio.run(cloud.propose("evolutivo"))
    assert view["proposals"] and view["tick"] == 0
    assert "series" not in view and "agents" not in view  # sin laboratorio no se serializa la simulación
