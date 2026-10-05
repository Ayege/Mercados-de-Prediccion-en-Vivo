"""Catálogo de regiones: costo relativo, disponibilidad y latencia hacia los usuarios.

- **Costo:** real. Es la proporción entre los precios de lista de Cloud Run por
  región (catálogo de Cloud Billing, 2026-10-05): nivel 1 = 1,0, nivel 2 = 1,4.
  El mercado real usa los precios absolutos, leídos en vivo.
- **Latencia y disponibilidad:** estimaciones plausibles, no medidas. La latencia
  real de cada nodo desplegado se ve en la tarjeta de infraestructura.
- **Recursos y zonas de usuarios:** de la simulación.
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
    cost: float  # proporción real de precios de Cloud Run frente a us-east1
    availability: float  # probabilidad de que la región esté arriba
    latency: dict[str, float] = field(hash=False)  # ms hasta cada zona de usuarios


REGIONS = {r.name: r for r in (
    Region("us-east1", 1.00, 0.995,
           {"caribe": 45, "norteamerica": 30, "sudamerica": 140, "europa": 95}),
    Region("us-central1", 1.00, 0.996,
           {"caribe": 70, "norteamerica": 35, "sudamerica": 160, "europa": 115}),
    Region("northamerica-northeast1", 1.40, 0.995,
           {"caribe": 65, "norteamerica": 40, "sudamerica": 170, "europa": 90}),
    Region("southamerica-east1", 1.40, 0.993,
           {"caribe": 110, "norteamerica": 130, "sudamerica": 25, "europa": 200}),
    Region("europe-west1", 1.00, 0.996,
           {"caribe": 120, "norteamerica": 90, "sudamerica": 210, "europa": 20}),
)}
