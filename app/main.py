"""Raíz de composición: el único lugar que conoce todas las capas y las conecta."""
from __future__ import annotations

from fastapi import FastAPI

from .adapters.memory import InMemoryRepository
from .adapters.oracle.mock import MockOracle
from .adapters.oracle.vertex import VertexOracle
from .application.ports import OracleGateway
from .application.service import MarketService
from .config import Settings
from .domain.verdict import AcceptancePolicy, CensusPolicy
from .entrypoints.http.api import create_app
from .seeds import seed


def build_oracle(settings: Settings) -> OracleGateway:
    policy = AcceptancePolicy(settings.min_confidence, settings.min_sources)
    if settings.uses_vertex:
        return VertexOracle(settings.project, settings.location, settings.model, policy)
    return MockOracle(policy)


def build_service(settings: Settings, oracle: OracleGateway | None = None) -> MarketService:
    return MarketService(
        InMemoryRepository(),
        oracle or build_oracle(settings),
        CensusPolicy(settings.min_census),
        starting_balance=settings.starting_balance,
        oracle_cooldown=settings.oracle_cooldown,
    )


def build(settings: Settings | None = None, service: MarketService | None = None,
          with_seed: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    service = service or build_service(settings)
    if with_seed:
        seed(service, settings.seed_set)
    return create_app(service, settings.presenter_key, settings.revision)


app = build()
