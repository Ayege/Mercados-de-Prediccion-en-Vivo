"""Topologías de despliegue: cuántas réplicas en cada región.

Dos generadores compiten por proponer topologías: un modelo generativo (puerto
`TopologyGenerator`) y una búsqueda evolutiva determinista (`evolve`). Ninguno
decide: `TopologyPolicy` evalúa cada propuesta y la acepta o la rechaza con
todas sus razones. Es el mismo patrón que el oráculo: el modelo propone, el
código dispone.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from math import prod

from .catalog import GEOS, REGIONS

REPLICA_COST = 8.0


@dataclass(frozen=True)
class Score:
    cost: float
    latency: float  # ms promedio, ponderado por dónde están los usuarios
    availability: float
    replicas: int
    regions: int
    value: float  # costo-desempeño: (1000 / latencia) por unidad de costo, ×100


def evaluate(replicas: dict[str, int]) -> Score:
    used = [r for r, n in replicas.items() if n > 0]
    total = sum(replicas.values())
    cost = sum(n * REPLICA_COST * REGIONS[r].cost for r, n in replicas.items())
    if not used:
        return Score(cost, float("inf"), 0.0, 0, 0, 0.0)
    latency = sum(share * min(REGIONS[r].latency[g] for r in used) for g, share in GEOS.items())
    availability = 1 - prod(1 - REGIONS[r].availability for r in used)
    value = (1000 / latency) / cost * 100 if cost else 0.0
    return Score(round(cost, 2), round(latency, 1), availability, total, len(used), round(value, 2))


@dataclass(frozen=True)
class Draft:
    """Lo que devuelve un generador antes de que nadie lo evalúe."""

    raw: object  # lo que el modelo dijo, ya parseado; None si no se pudo
    model: str
    trace: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass(frozen=True)
class Decision:
    accepted: bool
    replicas: dict[str, int] | None
    score: Score | None
    trace: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TopologyPolicy:
    budget: float = 70.0
    min_regions: int = 2
    min_availability: float = 0.9999
    max_latency: float = 75.0
    min_replicas: int = 4
    max_per_region: int = 6

    def parse(self, raw: object) -> tuple[dict[str, int] | None, list[str]]:
        """Valida la forma. Lo que no es un dict de región → entero se rechaza entero."""
        if not isinstance(raw, dict) or not isinstance(raw.get("replicas"), dict):
            return None, ["forma inválida: se esperaba {\"replicas\": {región: n}}"]
        problems, out = [], {}
        for region, n in raw["replicas"].items():
            if region not in REGIONS:
                problems.append(f"región inexistente: {region}")
            elif isinstance(n, bool) or not isinstance(n, int):
                problems.append(f"réplicas no enteras en {region}: {n!r}")
            elif not 0 <= n <= self.max_per_region:
                problems.append(f"{region}: {n} réplicas fuera de [0, {self.max_per_region}]")
            else:
                out[region] = n
        return (None, problems) if problems else (out, [])

    def violations(self, s: Score) -> list[str]:
        v = []
        if s.regions < self.min_regions:
            v.append(f"{s.regions} región(es) < {self.min_regions} requeridas")
        if s.replicas < self.min_replicas:
            v.append(f"{s.replicas} réplicas < {self.min_replicas} requeridas")
        if s.cost > self.budget:
            v.append(f"costo {s.cost:.1f} > presupuesto {self.budget:.1f}")
        if s.availability < self.min_availability:
            v.append(f"disponibilidad {s.availability:.5f} < {self.min_availability}")
        if s.latency > self.max_latency:
            v.append(f"latencia {s.latency:.0f} ms > {self.max_latency:.0f} ms")
        return v

    def check(self, raw: object) -> Decision:
        replicas, problems = self.parse(raw)
        if replicas is None:
            return Decision(False, None, None, [f"política: {p} → rechazada" for p in problems])
        s = evaluate(replicas)
        trace = [f"propuesta: {s.replicas} réplicas en {s.regions} región(es), costo {s.cost:.1f}, "
                 f"latencia {s.latency:.0f} ms, valor {s.value:.2f}"]
        bad = self.violations(s)
        if bad:
            return Decision(False, replicas, s, trace + [f"política: {b} → rechazada" for b in bad])
        return Decision(True, replicas, s, trace + ["política: aceptada"])


def evolve(policy: TopologyPolicy, rng: random.Random, generations: int = 30,
           size: int = 20) -> tuple[dict[str, int], list[float]]:
    """Algoritmo genético sobre topologías. Devuelve la mejor y el mejor valor por generación."""
    regions = list(REGIONS)

    def fitness(r: dict[str, int]) -> float:
        s = evaluate(r)
        bad = policy.violations(s)
        return s.value if not bad else -len(bad)

    def mutate(r: dict[str, int]) -> dict[str, int]:
        r = dict(r)
        region = rng.choice(regions)
        r[region] = min(policy.max_per_region, max(0, r[region] + rng.choice((-1, 1))))
        return r

    pop = [{g: rng.randint(0, 2) for g in regions} for _ in range(size)]
    best_curve = []
    for _ in range(generations):
        pop.sort(key=fitness, reverse=True)
        best_curve.append(round(fitness(pop[0]), 2))
        nxt = pop[:2]  # élite
        while len(nxt) < size:
            a, b = (max(rng.sample(pop, 3), key=fitness) for _ in range(2))
            child = {g: (a if rng.random() < 0.5 else b)[g] for g in regions}
            nxt.append(mutate(child) if rng.random() < 0.6 else child)
        pop = nxt
    pop.sort(key=fitness, reverse=True)
    return {r: n for r, n in pop[0].items() if n > 0}, best_curve
