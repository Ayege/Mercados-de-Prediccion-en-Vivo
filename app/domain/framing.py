"""Encuadre: el mismo hecho contado de dos maneras, y lo que eso le hace a quien lo lee.

Una pregunta puede llevar dos titulares sobre el mismo hecho: uno que empuja
hacia el SÍ y otro hacia el NO. Cada persona de la sala ve solo uno, asignado
al azar en bloques (el grupo más chico recibe a la siguiente persona; si están
empatados, decide un hash del nombre). Como la asignación no depende de lo que
cada quien cree, la diferencia de apuestas entre los dos grupos la causó el
titular, al menos en esta sala.

El modelo también lee noticias. `FramingPolicy` exige que el veredicto del
oráculo no cambie cuando se le muestra uno u otro titular: si cambia sin
evidencia nueva, el veredicto dependía de la redacción y no de los hechos.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

from .errors import MarketError
from .verdict import Verdict

ARMS = ("pro_si", "pro_no")  # qué titular vio cada grupo
LEAN = {"pro_si": "YES", "pro_no": "NO"}


@dataclass(frozen=True)
class Headline:
    text: str
    source: str  # el medio, o «titular de ensayo» si lo escribió el ponente
    url: str = ""

    def __post_init__(self) -> None:
        if not 8 <= len(self.text) <= 200:
            raise MarketError("el titular debe tener entre 8 y 200 caracteres")
        if not self.source.strip():
            raise MarketError("cada titular necesita su fuente: un medio real o «titular de ensayo»")
        if self.url and not self.url.startswith("https://"):
            raise MarketError("el enlace del titular debe ser https")


@dataclass(frozen=True)
class News:
    """Un titular tal como le llega al oráculo.

    `trusted` es el fallo que se quiere enseñar: un pipeline que le pasa la noticia
    al modelo como si fuera un hecho verificado, en vez de como dato no confiable.
    """

    headline: Headline
    lean: str  # YES o NO: hacia dónde empuja
    trusted: bool = False


@dataclass(frozen=True)
class Framing:
    pro_si: Headline
    pro_no: Headline

    def headline(self, arm: str) -> Headline:
        return self.pro_si if arm == "pro_si" else self.pro_no

    def news(self, trusted: bool = False) -> dict[str, News]:
        return {a: News(self.headline(a), LEAN[a], trusted) for a in ARMS}


@dataclass
class Exposure:
    """Quién vio qué titular y cuánto apostó cada grupo. Nunca sale por persona."""

    arms: dict[str, str] = field(default_factory=dict)  # persona → grupo
    spend: dict[str, dict[str, float]] = field(
        default_factory=lambda: {a: {"YES": 0.0, "NO": 0.0} for a in ARMS})
    traders: dict[str, set[str]] = field(default_factory=lambda: {a: set() for a in ARMS})

    def assign(self, who: str, market_id: str) -> str:
        """Aleatorización en bloques: los grupos nunca se separan por más de una persona."""
        if who in self.arms:
            return self.arms[who]
        sizes = {a: sum(1 for x in self.arms.values() if x == a) for a in ARMS}
        if sizes["pro_si"] != sizes["pro_no"]:
            arm = min(ARMS, key=lambda a: sizes[a])
        else:
            digest = hashlib.sha256(f"{market_id}:{who}".encode()).digest()
            arm = ARMS[digest[0] % 2]
        self.arms[who] = arm
        return arm

    def record(self, who: str, outcome: str, spend: float) -> None:
        arm = self.arms[who]
        self.spend[arm][outcome] += spend
        self.traders[arm].add(who)

    def summary(self) -> dict:
        """Por grupo: a cuántos les tocó, cuántos apostaron y qué parte del dinero fue al SÍ."""
        out = {}
        for a in ARMS:
            total = self.spend[a]["YES"] + self.spend[a]["NO"]
            out[a] = {
                "assigned": sum(1 for x in self.arms.values() if x == a),
                "traders": len(self.traders[a]),
                "yes_share": round(self.spend[a]["YES"] / total, 3) if total else None,
            }
        return out


@dataclass
class FramingExperiment:
    """Lo que una pregunta con encuadre lleva consigo: los titulares, los grupos y si ya
    se revelaron. La asignación ocurre al entrar o al crear la pregunta, nunca al leer."""

    framing: Framing
    exposure: Exposure = field(default_factory=Exposure)
    revealed: bool = False  # la proyección muestra los titulares al revelar o al resolver

    def assign(self, who: str, market_id: str) -> str:
        return self.exposure.assign(who, market_id)

    def headline_for(self, who: str) -> Headline | None:
        """Solo lectura: el titular de quien ya tiene grupo."""
        arm = self.exposure.arms.get(who)
        return None if arm is None else self.framing.headline(arm)

    def record(self, who: str, outcome: str, spend: float, market_id: str) -> None:
        self.assign(who, market_id)  # quien entró antes de que existiera la pregunta ya tiene grupo
        self.exposure.record(who, outcome, spend)

    def news(self, trusted: bool = False) -> dict[str, News]:
        return self.framing.news(trusted)


@dataclass(frozen=True)
class FramingPolicy:
    """El veredicto vale solo si no depende del titular que el modelo leyó."""

    def apply(self, neutral: Verdict, framed: dict[str, Verdict]) -> Verdict:
        if not neutral.decisive:
            return neutral
        trace = list(neutral.trace)
        for name, v in framed.items():
            trace.append(f"encuadre: con el titular {name.replace('_', '-')} el modelo dice {v.outcome} "
                         f"(confianza {v.confidence:.2f})")
        flipped = [name.replace("_", "-") for name, v in framed.items() if v.outcome != neutral.outcome]
        outcome = neutral.outcome
        if flipped:
            trace.append(f"política de encuadre: el veredicto cambió con el titular {' y '.join(flipped)}; "
                         "los hechos eran los mismos → UNRESOLVED")
            outcome = "UNRESOLVED"
        else:
            trace.append("política de encuadre: el veredicto no depende del titular")
        reads = {k: {"outcome": v.outcome, "confidence": round(v.confidence, 2)}
                 for k, v in ({"neutral": neutral} | framed).items()}
        return replace(neutral, outcome=outcome, trace=trace, framing=reads)
