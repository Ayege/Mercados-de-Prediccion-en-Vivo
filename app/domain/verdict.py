"""Veredictos y las políticas que deciden si se aceptan.

El modelo *propone*, el código *dispone*. Todo lo que decide si un veredicto
vale vive aquí, en Python puro, y no en el prompt ni en un adaptador.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

OUTCOMES = ("YES", "NO")
VALID = {"YES", "NO", "UNRESOLVED"}


@dataclass(frozen=True)
class Source:
    claim: str
    url: str
    domain: str


@dataclass
class Verdict:
    outcome: str
    confidence: float
    reasoning: str
    evidence: list[Source] = field(default_factory=list)
    model: str = ""
    trace: list[str] = field(default_factory=list)
    search_suggestions: str = ""

    @property
    def decisive(self) -> bool:
        return self.outcome in OUTCOMES

    @property
    def domains(self) -> set[str]:
        return {s.domain for s in self.evidence if s.domain}

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Proposal:
    """Lo que el modelo dice, antes de que nadie lo crea."""

    outcome: str
    confidence: float
    reasoning: str

    @classmethod
    def from_raw(cls, raw: dict) -> Proposal:
        try:
            conf = max(0.0, min(1.0, float(raw.get("confidence", 0))))
        except (TypeError, ValueError):
            conf = 0.0
        return cls(
            outcome=str(raw.get("outcome", "UNRESOLVED")).upper(),
            confidence=conf,
            reasoning=str(raw.get("reasoning", ""))[:1200],
        )


@dataclass(frozen=True)
class AcceptancePolicy:
    """Confianza mínima, fuentes independientes y fail-closed ante cualquier duda."""

    min_confidence: float = 0.8
    min_sources: int = 2

    def apply(
        self,
        proposal: Proposal,
        evidence: list[Source],
        model: str,
        trace: list[str] | None = None,
        suggestions: str = "",
    ) -> Verdict:
        trace = list(trace or [])
        outcome = proposal.outcome
        if outcome not in VALID:
            trace.append(f"política: resultado inválido '{outcome}' → UNRESOLVED")
            outcome = "UNRESOLVED"

        domains = {s.domain for s in evidence if s.domain}
        conf = proposal.confidence
        trace.append(f"veredicto propuesto: {outcome} (confianza {conf:.2f}, {len(domains)} dominios)")

        if outcome != "UNRESOLVED":
            if conf < self.min_confidence:
                trace.append(f"política: confianza {conf:.2f} < {self.min_confidence:.2f} → UNRESOLVED")
                outcome = "UNRESOLVED"
            elif len(domains) < self.min_sources:
                trace.append(
                    f"política: {len(domains)} dominio(s) < {self.min_sources} requeridos → UNRESOLVED"
                )
                outcome = "UNRESOLVED"
            else:
                trace.append(f"política: aceptado con {', '.join(sorted(domains))}")

        return Verdict(outcome, conf, proposal.reasoning, list(evidence), model, trace, suggestions)

    def unreachable(self, model: str, trace: list[str], evidence: list[Source] | None = None,
                    reasoning: str = "No se pudo consultar al oráculo.") -> Verdict:
        """Veredicto fail-closed cuando no hay propuesta que evaluar."""
        return Verdict("UNRESOLVED", 0.0, reasoning, list(evidence or []), model, trace)


@dataclass(frozen=True)
class CensusPolicy:
    """Resuelve preguntas de la sala con su censo privado. Misma idea: mínimo o nada."""

    min_responses: int = 5

    def tally(self, answers: list[bool], threshold: float) -> Verdict:
        n, yes = len(answers), sum(answers)
        share = yes / n if n else 0.0
        trace = [f"censo: {yes} de {n} respondieron SÍ ({share:.0%}); umbral {threshold:.0%}"]
        if n < self.min_responses:
            trace.append(f"política: {n} respuesta(s) < {self.min_responses} requeridas → UNRESOLVED")
            outcome = "UNRESOLVED"
        else:
            outcome = "YES" if share > threshold else "NO"
            trace.append(f"política: aceptado → {outcome}")
        return Verdict(
            outcome=outcome,
            confidence=1.0 if outcome != "UNRESOLVED" else 0.0,
            reasoning=f"{yes} de {n} personas de la sala respondieron SÍ en privado.",
            model="censo",
            trace=trace,
        )
