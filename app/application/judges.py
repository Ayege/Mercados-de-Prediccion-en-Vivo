"""Un solo juez para el mercado: la simulación o la infraestructura real, según el predicado."""
from __future__ import annotations

from ..domain.cloud.predicates import REAL
from ..domain.verdict import Verdict
from .ports import SimulationJudge


class CompositeJudge:
    def __init__(self, simulated: SimulationJudge, real: SimulationJudge | None):
        self.simulated = simulated
        self.real = real

    def judge(self, predicate: str) -> Verdict:
        if predicate not in REAL:
            return self.simulated.judge(predicate)
        if self.real is None:
            why = "la infraestructura real está apagada (INFRA_MODE=apagado)"
            return Verdict("UNRESOLVED", 0.0, why, model="infraestructura", trace=[f"{why} → UNRESOLVED"])
        return self.real.judge(predicate)
