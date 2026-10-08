"""LMSR (Logarithmic Market Scoring Rule) de Hanson: market maker automático.

C(q) = b * ln(sum_i exp(q_i / b))      -> función de costo
p_i  = exp(q_i / b) / sum_j exp(q_j / b) -> probabilidad implícita (precio)

Pérdida máxima del creador del mercado: b * ln(n)  (n = nº de resultados).
"""
from __future__ import annotations

import math


def cost(q: list[float], b: float) -> float:
    m = max(q)
    return m + b * math.log(sum(math.exp((x - m) / b) for x in q))


def prices(q: list[float], b: float) -> list[float]:
    m = max(q)
    e = [math.exp((x - m) / b) for x in q]
    s = sum(e)
    return [x / s for x in e]


def shares_for_spend(q: list[float], b: float, i: int, spend: float) -> float:
    """Acciones Δ del resultado i que se obtienen gastando `spend`.

    Resuelve C(q + Δ·e_i) = C(q) + spend en forma cerrada.
    """
    m = max(q)
    e = [math.exp((x - m) / b) for x in q]
    total = sum(e)
    rest = total - e[i]
    new_i = math.exp(spend / b) * total - rest
    return b * math.log(new_i) + m - q[i]


def spend_to_reach(q: list[float], b: float, i: int, target: float) -> float:
    """Cuánto hay que gastar en el resultado i (de dos) para que su precio llegue a `target`.

    En un mercado binario, p_i = target cuando q_i − q_j = b · ln(target / (1 − target)).
    Si el precio ya está en `target` o por encima, no hace falta gastar nada.
    """
    j = 1 - i
    delta = q[j] + b * math.log(target / (1 - target)) - q[i]
    if delta <= 0:
        return 0.0
    after = list(q)
    after[i] += delta
    return cost(after, b) - cost(q, b)
