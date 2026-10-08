"""Medios, dietas de medios y agentes que leen noticias antes de apostar.

Una pregunta puede nacer de las noticias del día: el modelo propone la pregunta
y busca cobertura en una lista de medios con su inclinación. La lista no la
decide el modelo ni el código: la define el ponente, con la fuente de cada
clasificación, y la pantalla la cita.

Cuatro agentes leen esa cobertura con dietas distintas (solo izquierda, solo
derecha, ambas, ninguna), estiman la probabilidad del SÍ y apuestan en el mismo
mercado que la sala. Lo que se ve es cuánto separa la dieta las creencias, y
al resolver, qué dieta ganó dinero.

Un titular nunca lo escribe el modelo: sale de un índice de noticias (Google
News), que lo atribuye al medio que lo publicó. El modelo solo elige titulares
por su número; no puede escribirlos ni cambiarlos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import lmsr
from .errors import MarketError

LEANS = ("izquierda", "derecha")
# Qué inclinaciones lee cada dieta.
DIETS = {"izquierda": ("izquierda",), "derecha": ("derecha",), "ambas": LEANS, "ninguna": ()}
# Los agentes llevan «:» en el nombre, que la audiencia no puede usar: nadie los suplanta.
AGENTS = {f"agente:{d}": d for d in DIETS}
DOMAIN = re.compile(r"^(?=.{3,80}$)([a-z0-9-]+\.)+[a-z]{2,}$")
# Índices de noticias aceptados: quién atribuye el titular al medio, y el host de sus enlaces.
INDEXES = {"Google News": "news.google.com"}


def host_of(url: str) -> str:
    """El host de una URL https, en minúsculas y sin «www.». Vacío si no es https."""
    m = re.match(r"^https://([^/:?#]+)", url or "")
    return m.group(1).lower().removeprefix("www.") if m else ""


@dataclass(frozen=True)
class Outlet:
    name: str
    domain: str
    lean: str
    source: str  # de dónde sale la clasificación

    def __post_init__(self) -> None:
        if self.lean not in LEANS:
            raise MarketError(f"inclinación inválida para {self.name}: {self.lean} (izquierda | derecha)")
        if not DOMAIN.match(self.domain):
            raise MarketError(f"dominio inválido para {self.name}: {self.domain}")
        if not self.name.strip() or not self.source.strip():
            raise MarketError("cada medio necesita nombre y la fuente de su clasificación")

    def owns(self, host: str) -> bool:
        return host == self.domain or host.endswith("." + self.domain)


@dataclass(frozen=True)
class MediaList:
    outlets: tuple[Outlet, ...] = ()
    source: str = ""  # quién definió la lista y con qué criterio
    rehearsal: bool = False  # medios ficticios para ensayar sin red

    @property
    def ready(self) -> bool:
        return all(any(o.lean == lean for o in self.outlets) for lean in LEANS)

    def outlet_for(self, url: str) -> Outlet | None:
        host = host_of(url)
        return next((o for o in self.outlets if host and o.owns(host)), None)

    def summary(self) -> dict:
        return {"ready": self.ready, "source": self.source, "rehearsal": self.rehearsal,
                "outlets": [{"name": o.name, "domain": o.domain, "lean": o.lean, "source": o.source}
                            for o in self.outlets]}


@dataclass(frozen=True)
class Article:
    """Un titular real de un medio de la lista.

    Sin `via`, el enlace es la página del propio medio. Con `via`, el titular y su
    atribución al medio vienen de ese índice de noticias, y el enlace es el suyo.
    """

    headline: str
    url: str
    outlet: Outlet
    via: str = ""

    def __post_init__(self) -> None:
        if self.via:
            if host_of(self.url) != INDEXES.get(self.via):
                raise MarketError("el enlace no pertenece al índice que atribuye el titular")
        elif not self.outlet.owns(host_of(self.url)):
            raise MarketError("el enlace no pertenece al medio")
        if not 8 <= len(self.headline) <= 300:
            raise MarketError("titular de largo inválido")


@dataclass
class NewsFind:
    """Lo que trae la búsqueda: la propuesta del modelo y los artículos verificados."""

    raw: dict | None
    articles: list[Article]
    trace: list[str]
    model: str = ""


@dataclass
class NewsDraft:
    id: str
    topic: str
    question: str
    criteria: str
    kind: str
    articles: list[Article]
    accepted: bool
    trace: list[str]
    model: str
    market_id: str | None = None  # cuando el ponente la abre


@dataclass(frozen=True)
class NewsPolicy:
    """Qué hace falta para abrir una pregunta salida de las noticias."""

    min_per_side: int = 1
    max_per_side: int = 3

    def check(self, draft_id: str, topic: str, find: NewsFind) -> NewsDraft:
        trace = list(find.trace)
        raw = find.raw or {}
        question = str(raw.get("pregunta", "")).strip()[:200]
        criteria = str(raw.get("criterio", "")).strip()[:600]
        kind = str(raw.get("tipo", "")).strip()
        articles = {lean: [a for a in find.articles if a.outlet.lean == lean][: self.max_per_side]
                    for lean in LEANS}
        problems = []
        if find.raw is None:
            trace.append("política: no hay pregunta propuesta → rechazada (fail-closed)")
            return NewsDraft(draft_id, topic, "", "", "", [], False, trace, find.model)
        if not (8 <= len(question) and question.endswith("?")):
            problems.append("la pregunta no es una pregunta de sí o no")
        if len(criteria) < 8:
            problems.append("falta el criterio de resolución")
        if kind not in ("presente", "futuro"):
            problems.append(f"tipo inválido «{kind}» (presente | futuro)")
        for lean, found in articles.items():
            if len(found) < self.min_per_side:
                problems.append(f"no hay titulares de medios de {lean}")
        for p in problems:
            trace.append(f"política: {p}")
        accepted = not problems
        trace.append("política: aceptada; la abre el ponente" if accepted
                     else "política: rechazada (fail-closed)")
        return NewsDraft(draft_id, topic, question, criteria, kind,
                         articles["izquierda"] + articles["derecha"], accepted, trace, find.model)


@dataclass(frozen=True)
class Estimate:
    """Lo que un agente cree tras leer su dieta. `p` es None si no se pudo leer."""

    p: float | None
    reasoning: str
    trace: list[str] = field(default_factory=list)


@dataclass
class AgentRead:
    agent: str
    diet: str
    read: list[Article]
    p: float | None
    reasoning: str
    price_before: float
    outcome: str | None = None  # qué compró
    stake: float = 0.0
    shares: float = 0.0


def stake_for(p: float | None, q: list[float], b: float, budget: float,
              min_edge: float = 0.05) -> tuple[str | None, float]:
    """Cuánto apuesta un agente: compra hasta que el precio llega a lo que cree, sin pasarse
    de su presupuesto. Si el precio ya está cerca de su creencia, no apuesta."""
    price = lmsr.prices(q, b)[0]
    if p is None or abs(p - price) < min_edge:
        return None, 0.0
    outcome = "YES" if p > price else "NO"
    target = p if outcome == "YES" else 1 - p
    return outcome, round(min(budget, lmsr.spend_to_reach(q, b, 0 if outcome == "YES" else 1, target)), 2)


def read_for(diet: str, coverage: list[Article]) -> list[Article]:
    return [a for a in coverage if a.outlet.lean in DIETS[diet]]
