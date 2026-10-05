"""Selección y mutación entre generaciones, y la dinámica del replicador para comparar.

El algoritmo genético conserva la élite y reemplaza al resto con hijos de
padres elegidos por torneo. La dinámica del replicador (teoría de juegos
evolutiva) predice cómo deberían cambiar las proporciones de cada estrategia
según su ganancia relativa. Mostrar ambas lado a lado deja ver cuándo la
evolución real se aparta de la teoría, por mutación, deriva o tamaño chico.
"""
from __future__ import annotations

import random
from math import exp, sqrt

from .agents import ARCHETYPES, Agent, Genome, QLearner


def shares(agents: list[Agent]) -> dict[str, float]:
    n = len(agents) or 1
    return {a: sum(x.archetype == a for x in agents) / n for a in ARCHETYPES}


def mean_fitness(agents: list[Agent]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for a in ARCHETYPES:
        group = [x.fitness for x in agents if x.archetype == a]
        out[a] = sum(group) / len(group) if group else None
    return out


def replicator(share: dict[str, float], fitness: dict[str, float | None]) -> dict[str, float]:
    """Replicador exponencial: x_i' ∝ x_i · exp((f_i − f̄) / σ).

    Escalar por la dispersión σ lo hace invariante a dónde esté el cero de la
    ganancia, que en esta simulación puede ser negativo.
    """
    present = {a: f for a, f in fitness.items() if f is not None and share[a] > 0}
    if not present:
        return dict(share)
    mean = sum(share[a] * f for a, f in present.items())
    sd = max(1.0, sqrt(sum(share[a] * (f - mean) ** 2 for a, f in present.items())))
    weight = {a: share[a] * exp((f - mean) / sd) for a, f in present.items()}
    total = sum(weight.values())
    return {a: weight.get(a, 0.0) / total for a in ARCHETYPES}


def next_generation(agents: list[Agent], rng: random.Random, generation: int,
                    elite_frac: float = 0.25, sigma: float = 0.08) -> None:
    """Reemplaza en sitio los genomas de los no-élite. Cada agente conserva su nodo."""
    ranked = sorted(agents, key=lambda a: a.fitness, reverse=True)
    elite = max(1, round(len(agents) * elite_frac))
    # Los padres salen de la generación que termina, no de los hijos ya escritos.
    parents = [(a.genome, a.fitness) for a in ranked]

    def tournament() -> Genome:
        return max(rng.sample(parents, min(3, len(parents))), key=lambda p: p[1])[0]

    for agent in ranked[elite:]:
        child = Genome.crossover(tournament(), tournament(), rng).mutate(rng, sigma)
        agent.genome = child
        agent.learner = QLearner()  # lo aprendido en vida no se hereda
        agent.offset = 0.0
        agent.born = generation
    for agent in agents:
        agent.fitness = 0.0
