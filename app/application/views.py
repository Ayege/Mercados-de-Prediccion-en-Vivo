"""Vistas de salida de los casos de uso: dicts planos, tomados dentro de la transacción.

Las respuestas individuales al censo nunca salen de aquí: solo su conteo.
"""
from __future__ import annotations

from ..domain.market import Account, Attempt, Market


def attempt_view(a: Attempt) -> dict:
    v = a.verdict
    return {
        "outcome": v.outcome,
        "price_yes": a.price_yes,
        "fault": a.fault,
        "reason": v.trace[-1] if v.trace else "",
        "sources": len(v.domains),
        "at": a.at,
    }


def market_view(m: Market) -> dict:
    last = m.last_attempt
    oracle = None
    if last:
        oracle = last.verdict.as_dict() | {"price_yes": last.price_yes, "fault": last.fault}
    return {
        "id": m.id,
        "question": m.question,
        "criteria": m.criteria,
        "kind": m.kind,
        "resolver": m.resolver,
        "threshold": m.threshold if m.resolved_by_census else None,
        "census_count": len(m.census),
        "b": m.b,
        "q": list(m.q),
        "prices": m.prices(),
        "status": m.status,
        "outcome": m.outcome,
        "history": list(m.history),
        "volume": round(m.volume, 2),
        "oracle": oracle,
        "attempts": [attempt_view(a) for a in m.attempts],
        "max_loss": round(m.max_loss, 2),
    }


def account_view(a: Account) -> dict:
    return {
        "name": a.name,
        "balance": round(a.balance, 4),
        "positions": {k: dict(v) for k, v in a.positions.items()},
    }
