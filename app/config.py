"""Configuración. El único lugar que lee variables de entorno (salvo ORACLE_MOCK_FORCE)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MEDIA = str(Path(__file__).parent / "medios.json")


@dataclass(frozen=True)
class Settings:
    project: str = ""
    backend: str = "vertex"
    location: str = "global"
    model: str = "gemini-3.8-flash"
    min_confidence: float = 0.8
    min_sources: int = 2
    min_census: int = 5
    seed_set: str = "oraculo"
    presenter_key: str = ""
    starting_balance: float = 1000.0
    oracle_cooldown: float = 30.0
    revision: str = "local"
    sim_seed: int = 7
    sim_agents: int = 12
    tick_seconds: float = 1.0
    infra_mode: str = "apagado"  # apagado | ensayo | plan | real
    node_image: str = ""
    node_service_account: str = ""
    rps_per_instance: float = 10.0
    infra_interval: float = 10.0
    infra_max_total_min: int = 2
    infra_max_per_region: int = 2
    infra_max_services: int = 3
    infra_ttl: float = 1800.0
    market_agents: int = 4
    market_max_warm: int = 1
    market_max_requests: int = 12
    production: bool = False  # True en Cloud Run (K_SERVICE): se exigen los controles
    api_docs: bool = True
    vigil_account: str = ""  # cuenta de servicio de Cloud Scheduler, para verificar su OIDC
    vigil_audience: str = ""
    media_file: str = DEFAULT_MEDIA  # la lista de medios y su inclinación, definida por el ponente
    agent_budget: float = 200.0  # créditos que arriesga cada agente de noticias por pregunta
    room_code: str = "auto"  # «auto»: se genera al arrancar; vacío: sin código (solo en local)

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            project=env.get("GOOGLE_CLOUD_PROJECT", ""),
            backend=env.get("ORACLE_BACKEND", "vertex"),
            location=env.get("VERTEX_LOCATION", "global"),
            model=env.get("ORACLE_MODEL", "gemini-3.8-flash"),
            min_confidence=float(env.get("ORACLE_MIN_CONFIDENCE", "0.8")),
            min_sources=int(env.get("ORACLE_MIN_SOURCES", "2")),
            min_census=int(env.get("CENSUS_MIN_RESPONSES", "5")),
            seed_set=env.get("SEED_SET", "oraculo"),
            presenter_key=env.get("PRESENTER_KEY", ""),
            revision=env.get("K_REVISION", "local"),
            sim_seed=int(env.get("SIM_SEED", "7")),
            sim_agents=int(env.get("SIM_AGENTS", "12")),
            tick_seconds=float(env.get("SIM_TICK_SECONDS", "1.0")),
            infra_mode=env.get("INFRA_MODE", "apagado"),
            node_image=env.get("NODO_IMAGEN", ""),
            node_service_account=env.get("NODO_CUENTA", ""),
            rps_per_instance=float(env.get("INFRA_RPS_POR_INSTANCIA", "10")),
            infra_interval=float(env.get("INFRA_INTERVALO", "10")),
            infra_max_total_min=int(env.get("INFRA_MAX_INSTANCIAS_MINIMAS", "2")),
            infra_max_per_region=int(env.get("INFRA_MAX_POR_REGION", "2")),
            infra_max_services=int(env.get("INFRA_MAX_SERVICIOS", "3")),
            infra_ttl=float(env.get("INFRA_TTL_SEGUNDOS", "1800")),
            market_agents=int(env.get("MERCADO_AGENTES", "4")),
            market_max_warm=int(env.get("MERCADO_MAX_CALIENTES", "1")),
            market_max_requests=int(env.get("MERCADO_MAX_PETICIONES", "12")),
            production=bool(env.get("K_SERVICE")),
            api_docs=env.get("API_DOCS", "0" if env.get("K_SERVICE") else "1") == "1",
            vigil_account=env.get("VIGILIA_CUENTA", ""),
            vigil_audience=env.get("VIGILIA_AUDIENCIA", ""),
            media_file=env.get("MEDIOS_ARCHIVO", DEFAULT_MEDIA),
            agent_budget=float(env.get("AGENTES_PRESUPUESTO", "200")),
            room_code=env.get("SALA_CODIGO", "auto"),
        )

    def check(self) -> None:
        """Falla cerrado: en producción, o con infraestructura real, sin clave fuerte no arranca.
        En producción, además, nada simulado: oráculo, noticias e infraestructura reales."""
        needs_key = self.production or self.infra_mode in ("plan", "real")
        if needs_key and len(self.presenter_key) < 32:
            raise RuntimeError("PRESENTER_KEY debe tener al menos 32 caracteres en producción o con "
                               "INFRA_MODE=plan|real (genera una con: openssl rand -hex 16)")
        if self.production and not self.room_code.strip():
            raise RuntimeError("SALA_CODIGO no puede estar vacío en producción: sin código, cualquiera "
                               "en internet puede llenar la sala")
        if self.production and not self.uses_vertex:
            raise RuntimeError("En producción todo es real: hace falta GOOGLE_CLOUD_PROJECT y "
                               "ORACLE_BACKEND=vertex (sin oráculo, editor ni lectores simulados)")
        if self.production and self.infra_mode != "real":
            raise RuntimeError("En producción todo es real: INFRA_MODE debe ser «real» "
                               f"(está en «{self.infra_mode}»)")
        if self.infra_mode == "real" and self.vigil_account and not self.vigil_audience:
            raise RuntimeError("VIGILIA_CUENTA necesita VIGILIA_AUDIENCIA (la URL de la vigilia)")

    @property
    def uses_vertex(self) -> bool:
        return bool(self.project) and self.backend != "mock"
