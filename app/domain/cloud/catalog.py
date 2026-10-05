"""Catálogo del mundo simulado: recursos, regiones y dónde están los usuarios.

Los números son plausibles, no reales. Están para que los compromisos entre
costo, latencia y disponibilidad existan y se puedan ver.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Costo base por unidad y tick de cada recurso.
RESOURCES = {"cpu": 1.0, "almacenamiento": 0.4, "ancho_banda": 0.7}

# Qué fracción de los usuarios está en cada zona.
GEOS = {"caribe": 0.40, "norteamerica": 0.35, "sudamerica": 0.15, "europa": 0.10}


@dataclass(frozen=True)
class Region:
    name: str
    cost: float  # multiplicador sobre el costo base
    availability: float  # probabilidad de que la región esté arriba
    latency: dict[str, float] = field(hash=False)  # ms hasta cada zona de usuarios


REGIONS = {r.name: r for r in (
    Region("us-east1", 1.00, 0.995,
           {"caribe": 45, "norteamerica": 30, "sudamerica": 140, "europa": 95}),
    Region("us-central1", 0.92, 0.996,
           {"caribe": 70, "norteamerica": 35, "sudamerica": 160, "europa": 115}),
    Region("northamerica-northeast1", 1.05, 0.995,
           {"caribe": 65, "norteamerica": 40, "sudamerica": 170, "europa": 90}),
    Region("southamerica-east1", 1.35, 0.993,
           {"caribe": 110, "norteamerica": 130, "sudamerica": 25, "europa": 200}),
    Region("europe-west1", 1.10, 0.996,
           {"caribe": 120, "norteamerica": 90, "sudamerica": 210, "europa": 20}),
)}
