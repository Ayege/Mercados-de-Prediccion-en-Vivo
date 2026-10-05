"""Generador simulado: ensayos sin red. Alterna propuestas buenas y malas a propósito.

Cada propuesta mala ejercita una regla distinta de `TopologyPolicy`, para
poder mostrar en el escenario cómo el código rechaza al modelo.
"""
from __future__ import annotations

from ...domain.cloud.topology import Draft

PROPOSALS = [
    ({"replicas": {"us-east1": 2, "us-central1": 2}},
     "Dos regiones baratas cerca del Caribe y de Norteamérica."),
    ({"replicas": {"us-east1": 5}},
     "Todo en la región más cercana: menos latencia y menos complejidad."),
    ({"replicas": {"us-east1": 2, "marte-central1": 2}},
     "Una región nueva con capacidad ociosa a muy buen precio."),
    ({"replicas": {"us-east1": 4, "southamerica-east1": 4, "europe-west1": 3}},
     "Máxima cobertura global para minimizar latencia en todas las zonas."),
    ({"replicas": {"us-east1": 3, "southamerica-east1": 1, "us-central1": 1}},
     "Concentrar en us-east1 y cubrir Sudamérica con una réplica."),
    (None, ""),  # el modelo respondió prosa: no hay nada que evaluar
]


class MockTopologyGenerator:
    name = "mock"
    model = "mock"

    def __init__(self) -> None:
        self.calls = 0

    async def propose(self, brief: dict) -> Draft:
        raw, why = PROPOSALS[self.calls % len(PROPOSALS)]
        self.calls += 1
        trace = ["generador simulado, sin red"]
        if raw is None:
            trace.append("respuesta no parseable → sin propuesta (fail-closed)")
            return Draft(None, self.model, trace)
        return Draft(raw, self.model, trace + ["propuesta recibida; la decide la política, no el modelo"],
                     f"[Simulación] {why}")
