"""Juegos de preguntas. Qué charla das decide qué preguntas siembras.

Ver "Qué afirmar desde el escenario" en el README. Se elige con SEED_SET.
"""
from __future__ import annotations

from .application.service import MarketService

KUBERNETES = (
    "¿Se publicó Kubernetes v1.36 antes del 30 de septiembre de 2026?",
    "SÍ si existe una release estable v1.36.0 en github.com/kubernetes/kubernetes "
    "con fecha igual o anterior al 30/09/2026.",
    "presente",
)
PYTHON = (
    "¿Se publicó Python 3.15.0 (versión final) antes del 15 de octubre de 2026?",
    "SÍ si python.org muestra la release 3.15.0 final con fecha igual o anterior al 15/10/2026.",
    "presente",
)
DOLAR = (
    "¿Cerrará el USD/DOP por encima de 65 el 31 de diciembre de 2026?",
    "SÍ si la tasa de venta publicada por el Banco Central de la República Dominicana "
    "para el 31/12/2026 es mayor que 65.00. Antes de esa fecha no se puede resolver.",
    "futuro",
)
VIERNES = (
    "¿Más de la mitad de esta sala desplegó a producción un viernes en los últimos 30 días?",
    "Censo privado de la sala: SÍ si más del 50% de quienes respondan dice que sí.",
    "sala",
)
LLM = (
    "¿Más de la mitad de esta sala hizo merge esta semana de código generado por un LLM "
    "sin reescribirlo?",
    "Censo privado de la sala: SÍ si más del 50% de quienes respondan dice que sí.",
    "sala",
)
ROLLBACK = (
    "¿Más de la mitad de esta sala tuvo que revertir un despliegue en el último trimestre?",
    "Censo privado de la sala: SÍ si más del 50% de quienes respondan dice que sí.",
    "sala",
)
SEEDS = {
    # Charla sobre el oráculo: creencia contra evidencia, y el sistema negándose a responder.
    "oraculo": [KUBERNETES, PYTHON, DOLAR],
    # Charla sobre el mecanismo: información dispersa que ningún buscador tiene.
    "agregacion": [VIERNES, LLM, ROLLBACK],
    # Un ejemplo de cada tipo.
    "mixta": [PYTHON, DOLAR, VIERNES],
}


def seed(service: MarketService, seed_set: str) -> None:
    # Todos abren en 50 %: si el precio se mueve, lo movió la sala, no la casa.
    if seed_set not in SEEDS:
        raise ValueError(f"SEED_SET desconocido: {seed_set} (opciones: {', '.join(SEEDS)})")
    for question, criteria, kind in SEEDS[seed_set]:
        service.create(question, criteria, kind=kind)
