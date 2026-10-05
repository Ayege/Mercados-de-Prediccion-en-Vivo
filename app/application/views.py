"""Vistas de salida de los casos de uso: dicts planos, tomados dentro de la transacción.

Las respuestas individuales al censo nunca salen de aquí: solo su conteo.
"""
from __future__ import annotations

from ..domain.cloud.evolution import shares
from ..domain.cloud.simulation import FAULTS as SIM_FAULTS
from ..domain.cloud.simulation import PREDICATES, Simulation
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
        "predicate": m.predicate,
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


# --- nube simulada ----------------------------------------------------------------

def _r(x: float | None, nd: int = 2) -> float | None:
    return None if x is None else round(x, nd)


def _score(s) -> dict | None:
    if s is None:
        return None
    return {"cost": s.cost, "latency": s.latency, "availability": round(s.availability, 6),
            "replicas": s.replicas, "regions": s.regions, "value": s.value}


def simulation_view(sim: Simulation, running: bool, generator) -> dict:
    series = sim.series
    errors = sim.errors
    mape = naive = None
    if errors:
        mape = sum(abs(r - p) / r for r, p, _ in errors) / len(errors)
        naive = sum(abs(r - n) / r for r, _, n in errors) / len(errors)
    current = sim.policy.check({"replicas": sim.topology})
    faults = {f.id: f for f in sim.faults}
    return {
        "running": running,
        "tick": sim.tick_n,
        "generation": sim.generation,
        "seed": sim.seed,
        "generator": {"name": generator.name, "model": generator.model},
        "series": {
            "tick": list(series.tick),
            "demand": {r: [_r(x) for x in v] for r, v in series.demand.items()},
            "forecast": {r: [_r(x) for x in v] for r, v in series.forecast.items()},
            "price": {r: [_r(x) for x in v] for r, v in series.price.items()},
            "unmet": [_r(x) for x in series.unmet],
        },
        "forecast_error": {"holt_winters": _r(mape, 3), "ingenuo_estacional": _r(naive, 3),
                           "window": len(errors)},
        "totals": {"served": round(sim.served, 1), "unmet": round(sim.unmet, 1)},
        "agents": [
            {
                "id": a.id, "region": a.region, "archetype": a.archetype, "born": a.born,
                "genome": a.genome.as_dict(), "offset": round(a.offset, 2), "markup": round(a.markup, 2),
                "fitness": round(a.fitness, 1), "committed": round(a.committed, 2),
                "node": {
                    "latency": round(sim.nodes[a.id].latency, 1),
                    "status": ("reemplazando" if sim.drained(a)
                               else "con falla" if sim.nodes[a.id].fault else "sano"),
                },
            }
            for a in sorted(sim.agents, key=lambda a: a.fitness, reverse=True)
        ],
        "generations": [
            {"number": g.number, "tick": g.tick, "shares": g.shares,
             "fitness": {k: _r(v, 1) for k, v in g.fitness.items()},
             "predicted": {k: round(v, 3) for k, v in g.predicted.items()},
             "best": g.best, "best_genome": g.best_genome, "best_fitness": g.best_fitness}
            for g in sim.generations
        ],
        "shares_now": shares(sim.agents),
        "contracts": [
            {"tick": c.tick, "qty": c.qty, "payment": c.payment, "willing": c.willing, "members": c.members}
            for c in sim.contracts[-8:]
        ][::-1],
        "contracts_won": sum(c.members is not None for c in sim.contracts),
        "contracts_total": len(sim.contracts),
        "faults": [{"id": f.id, "kind": f.kind, "target": f.target, "tick": f.tick, "cleared": f.cleared}
                   for f in sim.faults][::-1],
        "incidents": [
            {"id": i.id, "signal": i.signal, "target": i.target, "tick": i.tick, "z": i.z,
             "action": i.action, "repaired": i.repaired, "fault": i.fault,
             "detected_after": (i.tick - faults[i.fault].tick) if i.fault else None}
            for i in sim.incidents[-12:]
        ][::-1],
        "false_positives": sum(i.fault is None for i in sim.incidents),
        "topology": {"replicas": sim.topology, "score": _score(current.score),
                     "compliant": current.accepted, "violations": current.trace},
        "proposals": [
            {"id": p.id, "source": p.source, "model": p.model, "tick": p.tick,
             "accepted": p.decision.accepted, "adopted": p.adopted, "replicas": p.decision.replicas,
             "score": _score(p.decision.score), "trace": p.trace, "reasoning": p.reasoning}
            for p in sim.proposals[-6:]
        ][::-1],
        "predicates": PREDICATES,
        "fault_kinds": SIM_FAULTS,
    }
