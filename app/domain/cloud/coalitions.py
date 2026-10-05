"""Coaliciones: contratos que ningún agente cubre solo, repartidos por valor de Shapley.

Un contrato pide más cpu de la que tiene cualquier agente y exige redundancia:
ninguna región puede servir más del 60 %. Los agentes dispuestos forman una
coalición, y la ganancia se reparte según la contribución marginal promedio de
cada uno a todas las coaliciones posibles (Shapley, exacto: como mucho 5 miembros).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from itertools import combinations
from math import factorial

MAX_MEMBERS = 5
MAX_REGION_SHARE = 0.6


@dataclass(frozen=True)
class Contract:
    qty: float
    payment: float


@dataclass(frozen=True)
class Member:
    agent: str
    region: str
    capacity: float
    unit_cost: float


@dataclass(frozen=True)
class Coalition:
    members: tuple[str, ...]
    value: float
    shares: dict[str, float]
    allocation: dict[str, float]


def serve(members: list[Member], contract: Contract) -> dict[str, float] | None:
    """Asignación más barata que respeta el tope por región. None si no alcanza."""
    cap_region = MAX_REGION_SHARE * contract.qty
    by_region: dict[str, float] = {}
    alloc: dict[str, float] = {}
    remaining = contract.qty
    for m in sorted(members, key=lambda m: (m.unit_cost, m.agent)):
        room = cap_region - by_region.get(m.region, 0.0)
        take = min(m.capacity, room, remaining)
        if take > 0:
            alloc[m.agent] = take
            by_region[m.region] = by_region.get(m.region, 0.0) + take
            remaining -= take
    return alloc if remaining <= 1e-9 else None


def value(members: list[Member], contract: Contract) -> float:
    alloc = serve(members, contract)
    if alloc is None:
        return 0.0
    cost = sum(alloc[m.agent] * m.unit_cost for m in members if m.agent in alloc)
    return max(0.0, contract.payment - cost)


def shapley(players: list[str], v: Callable[[frozenset[str]], float]) -> dict[str, float]:
    n = len(players)
    phi = dict.fromkeys(players, 0.0)
    for p in players:
        others = [q for q in players if q != p]
        for k in range(n):
            w = factorial(k) * factorial(n - k - 1) / factorial(n)
            for subset in combinations(others, k):
                s = frozenset(subset)
                phi[p] += w * (v(s | {p}) - v(s))
    return phi


def form(contract: Contract, willing: list[Member]) -> Coalition | None:
    """Suma a los dispuestos más baratos hasta que el contrato sea rentable y cubierto."""
    chosen: list[Member] = []
    for m in sorted(willing, key=lambda m: (m.unit_cost, m.agent)):
        chosen.append(m)
        if value(chosen, contract) > 0:
            break
        if len(chosen) == MAX_MEMBERS:
            return None
    else:
        return None

    index = {m.agent: m for m in chosen}

    @cache
    def v(s: frozenset[str]) -> float:
        return value([index[a] for a in sorted(s)], contract)

    names = [m.agent for m in chosen]
    return Coalition(tuple(names), v(frozenset(names)), shapley(names, v), serve(chosen, contract) or {})
