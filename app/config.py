"""Configuración. El único lugar que lee variables de entorno (salvo ORACLE_MOCK_FORCE)."""
from __future__ import annotations

import os
from dataclasses import dataclass


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
        )

    @property
    def uses_vertex(self) -> bool:
        return bool(self.project) and self.backend != "mock"
