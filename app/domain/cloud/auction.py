"""Subasta de precio uniforme: la demanda se llena con las ofertas más baratas.

Todos los vendedores aceptados cobran el precio de la última oferta aceptada.
Ojo: esta subasta la liquida un subastador central, así que el mercado de
recursos *no* es descentralizado. Lo descentralizado son las coaliciones.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ask:
    agent: str
    price: float
    qty: float


@dataclass(frozen=True)
class Clearing:
    price: float | None
    fills: dict[str, float] = field(default_factory=dict)
    served: float = 0.0
    unmet: float = 0.0


def clear(asks: list[Ask], demand: float, reservation: float) -> Clearing:
    """Llena `demand` con las ofertas más baratas que no superen `reservation`."""
    fills: dict[str, float] = {}
    remaining, price = demand, None
    for a in sorted(asks, key=lambda a: (a.price, a.agent)):
        if remaining <= 1e-9 or a.price > reservation:
            break
        if a.qty <= 0:
            continue
        take = min(a.qty, remaining)
        fills[a.agent] = take
        remaining -= take
        price = a.price
    return Clearing(price, fills, demand - remaining, remaining)
