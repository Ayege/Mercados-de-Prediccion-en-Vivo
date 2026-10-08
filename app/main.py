"""Raíz de composición: el único lugar que conoce todas las capas y las conecta."""
from __future__ import annotations

from fastapi import FastAPI

from .adapters.google_auth import verify_google_oidc
from .adapters.infra.cloudrun import CloudRunNodeGateway
from .adapters.infra.fake import FakeNodeGateway
from .adapters.memory import InMemoryRepository
from .adapters.news import media_list
from .adapters.news.mock import REHEARSAL, MockNewsDesk, MockNewsReader
from .adapters.news.vertex import VertexNewsDesk, VertexNewsReader
from .adapters.oracle.mock import MockOracle
from .adapters.oracle.vertex import VertexOracle
from .adapters.prices import CloudBillingPrices, FixedPrices
from .adapters.topology.mock import MockTopologyGenerator
from .adapters.topology.vertex import VertexTopologyGenerator
from .adapters.vertex_client import VertexClient
from .application.accounts import new_room_code
from .application.cloud import CloudService
from .application.infra import InfraController
from .application.judges import CompositeJudge
from .application.news import NewsService
from .application.ports import OracleGateway, TopologyGenerator
from .application.real_market import RealMarket
from .application.service import MarketService
from .config import Settings
from .domain.cloud.infra import ActuationPolicy
from .domain.cloud.real_market import MarketBudget
from .domain.cloud.simulation import Simulation
from .domain.verdict import AcceptancePolicy, CensusPolicy
from .entrypoints.http.api import create_app
from .seeds import seed


def build_oracle(settings: Settings) -> OracleGateway:
    policy = AcceptancePolicy(settings.min_confidence, settings.min_sources)
    if settings.uses_vertex:
        return VertexOracle(VertexClient(settings.project, settings.location, settings.model), policy)
    return MockOracle(policy)


def build_generator(settings: Settings) -> TopologyGenerator:
    if settings.uses_vertex:
        return VertexTopologyGenerator(VertexClient(settings.project, settings.location, settings.model))
    return MockTopologyGenerator()


def build_cloud(settings: Settings) -> CloudService:
    sim = Simulation(seed=settings.sim_seed, n_agents=settings.sim_agents)
    return CloudService(sim, build_generator(settings), settings.tick_seconds)


def build_infra(settings: Settings, cloud: CloudService) -> InfraController | None:
    """La infraestructura real solo existe si se pide explícitamente."""
    mode = settings.infra_mode
    if mode == "apagado":
        return None
    if mode == "ensayo":
        gateway = FakeNodeGateway()
        prices = FixedPrices()
    elif mode in ("plan", "real"):
        required = {"GOOGLE_CLOUD_PROJECT": settings.project, "NODO_IMAGEN": settings.node_image,
                    "NODO_CUENTA": settings.node_service_account}
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"INFRA_MODE={mode} necesita {', '.join(missing)}")
        gateway = CloudRunNodeGateway(settings.project, settings.node_image,
                                      settings.node_service_account, validate_only=mode == "plan")
        prices = CloudBillingPrices(settings.project)
    else:
        raise RuntimeError(f"INFRA_MODE desconocido: {mode} (apagado | ensayo | plan | real)")
    policy = ActuationPolicy(max_total_min=settings.infra_max_total_min,
                             max_max_per_region=settings.infra_max_per_region,
                             max_services=settings.infra_max_services)
    budget = MarketBudget(max_agents=settings.market_agents, max_warm=settings.market_max_warm,
                          max_requests=settings.market_max_requests)
    market = RealMarket(gateway, prices, budget, cycle_seconds=settings.infra_interval)
    return InfraController(gateway, lambda: dict(cloud.sim.topology), mode, policy,
                           settings.rps_per_instance, settings.infra_interval, ttl=settings.infra_ttl,
                           market=market)


def build_news(settings: Settings, service: MarketService) -> NewsService:
    """En producción, la lista de medios. En ensayo, siempre dos medios ficticios: el editor
    simulado inventa titulares, y nunca deben aparecer junto a nombres de medios reales."""
    media = media_list.load(settings.media_file)
    if settings.uses_vertex:
        client = VertexClient(settings.project, settings.location, settings.model)
        desk, reader = VertexNewsDesk(client), VertexNewsReader(client)
    else:
        desk, reader = MockNewsDesk(), MockNewsReader()
        media = REHEARSAL
    return NewsService(service, service.repo, desk, reader, media, agent_budget=settings.agent_budget,
                       cooldown=settings.oracle_cooldown)


def build_service(settings: Settings, oracle: OracleGateway | None = None,
                  cloud: CloudService | None = None, infra: InfraController | None = None) -> MarketService:
    return MarketService(
        InMemoryRepository(),
        oracle or build_oracle(settings),
        CensusPolicy(settings.min_census),
        judge=CompositeJudge(cloud, infra) if cloud else None,
        starting_balance=settings.starting_balance,
        oracle_cooldown=settings.oracle_cooldown,
        room_code=new_room_code() if settings.room_code.strip().lower() == "auto" else settings.room_code,
    )


def build(settings: Settings | None = None, service: MarketService | None = None,
          cloud: CloudService | None = None, infra: InfraController | None = None,
          with_seed: bool = True) -> FastAPI:
    """Si pasas `service`, pasa también la `cloud` y la `infra` que usa como juez."""
    settings = settings or Settings.from_env()
    settings.check()
    cloud = cloud or build_cloud(settings)
    if infra is None and service is None:
        infra = build_infra(settings, cloud)
    service = service or build_service(settings, cloud=cloud, infra=infra)
    if with_seed:
        seed(service, settings.seed_set)
    scheduler_check = None
    if settings.vigil_account:
        async def scheduler_check(token: str) -> bool:
            return await verify_google_oidc(token, settings.vigil_audience, settings.vigil_account)
    return create_app(service, cloud, infra, settings.presenter_key, settings.revision,
                      docs=settings.api_docs, scheduler_check=scheduler_check,
                      news=build_news(settings, service))


app = build()
