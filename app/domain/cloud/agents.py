"""Agentes proveedores: un genoma que hereda la especie y un Q-learner que aprende en vida.

- El genoma (evolución, entre generaciones) fija la estrategia de base: margen,
  reserva de capacidad, disposición a cooperar y cuánto confía en la predicción.
- El Q-learner (refuerzo, dentro de una vida) ajusta el margen tick a tick según
  la escasez prevista y cuánto vendió.

Los hijos heredan el genoma pero no lo aprendido: es evolución darwiniana.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, fields, replace

from .catalog import REGIONS, RESOURCES

# Rango de cada gen.
GENES = {
    "markup": (0.0, 1.5),  # margen sobre el costo
    "reserva": (0.0, 0.5),  # capacidad extra que mantiene encendida
    "cooperacion": (0.0, 1.0),  # probabilidad de entrar en coaliciones
    "prevision": (0.0, 1.0),  # cuánto escala y cobra según la demanda prevista
}
ARCHETYPES = ("cooperativo", "agresivo", "previsor", "austero")
ACTIONS = (-0.1, 0.0, 0.1)  # cambio del ajuste de margen aprendido


@dataclass(frozen=True)
class Genome:
    markup: float
    reserva: float
    cooperacion: float
    prevision: float

    @classmethod
    def random(cls, rng: random.Random) -> Genome:
        return cls(**{g: rng.uniform(lo, hi) for g, (lo, hi) in GENES.items()})

    def clipped(self) -> Genome:
        return Genome(**{g: min(hi, max(lo, getattr(self, g))) for g, (lo, hi) in GENES.items()})

    def mutate(self, rng: random.Random, sigma: float) -> Genome:
        """Ruido gaussiano proporcional al rango de cada gen."""
        changes = {g: getattr(self, g) + rng.gauss(0, sigma * (hi - lo)) for g, (lo, hi) in GENES.items()}
        return replace(self, **changes).clipped()

    @staticmethod
    def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
        return Genome(**{f.name: getattr(a if rng.random() < 0.5 else b, f.name) for f in fields(Genome)})

    def as_dict(self) -> dict[str, float]:
        return {f.name: round(getattr(self, f.name), 3) for f in fields(self)}


def archetype(g: Genome) -> str:
    """Etiqueta legible de una estrategia. Es una lectura del genoma, no un gen."""
    if g.cooperacion >= 0.6:
        return "cooperativo"
    if g.markup >= 0.8:
        return "agresivo"
    if g.prevision >= 0.6:
        return "previsor"
    return "austero"


@dataclass
class QLearner:
    """Q-learning tabular. Estado: (escasez prevista, cuánto vendió). Acción: mover el margen."""

    alpha: float = 0.2
    gamma: float = 0.8
    epsilon: float = 0.1
    q: dict[tuple[int, int], list[float]] = field(default_factory=dict)

    def values(self, state: tuple[int, int]) -> list[float]:
        return self.q.setdefault(state, [0.0] * len(ACTIONS))

    def act(self, state: tuple[int, int], rng: random.Random) -> int:
        if rng.random() < self.epsilon:
            return rng.randrange(len(ACTIONS))
        v = self.values(state)
        return v.index(max(v))

    def learn(self, state: tuple[int, int], action: int, reward: float, nxt: tuple[int, int]) -> None:
        v = self.values(state)
        v[action] += self.alpha * (reward + self.gamma * max(self.values(nxt)) - v[action])


@dataclass
class Agent:
    id: str
    region: str
    capacity: dict[str, float]
    genome: Genome
    learner: QLearner = field(default_factory=QLearner)
    offset: float = 0.0  # ajuste de margen aprendido por refuerzo, en [-0.5, 0.5]
    fitness: float = 0.0  # ganancia en la generación actual
    born: int = 0  # generación en la que nació
    committed: float = 0.0  # cpu comprometida con una coalición
    committed_until: int = -1
    last_sold: int = 0  # bucket de venta del tick anterior
    pending: tuple[tuple[int, int], int] | None = None  # (estado, acción) a recompensar

    @property
    def archetype(self) -> str:
        return archetype(self.genome)

    @property
    def markup(self) -> float:
        return max(0.0, self.genome.markup + self.offset)

    def unit_cost(self, resource: str) -> float:
        return RESOURCES[resource] * REGIONS[self.region].cost

    def ask_price(self, resource: str, scarcity: float) -> float:
        premium = self.genome.prevision * max(0.0, scarcity - 0.6) * 2
        return self.unit_cost(resource) * (1 + self.markup + premium)

    def active_capacity(self, resource: str, forecast_share: float, emergency: bool) -> float:
        """Autoescalado: cuánto encender según la demanda prevista para este agente."""
        cap = self.capacity[resource]
        if resource == "cpu":
            cap = max(0.0, cap - self.committed)
        if emergency:
            return cap
        target = min(cap, forecast_share * (1 + self.genome.reserva) * 1.3)
        return (1 - self.genome.prevision) * cap + self.genome.prevision * target
