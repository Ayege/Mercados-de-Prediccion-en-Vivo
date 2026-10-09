"""Entidades del mercado: el mercado en sí y la cuenta de cada participante.

Cada mercado declara qué tipo de pregunta es, porque eso cambia qué mide el precio:

- `presente`: la respuesta ya existe y es verificable; nadie en la sala la sabe con
  certeza. El precio agrega conocimiento disperso sobre el presente (Hayek).
  Lo resuelve el oráculo con evidencia.
- `futuro`: hoy no tiene respuesta. Está para que el oráculo diga UNRESOLVED.
- `sala`: la respuesta está repartida entre los asistentes y no se puede buscar.
  Lo resuelve un censo privado de la propia sala, no el oráculo.
- `simulacion`: qué harán los agentes de la nube simulada. Nadie lo sabe porque
  el comportamiento es emergente. Lo resuelve el propio código de la simulación.

Una pregunta `presente` o `futuro` puede llevar además un encuadre: dos titulares
sobre el mismo hecho, y cada persona ve solo uno (ver `framing.py`). O puede nacer
de las noticias del día, con su cobertura y los agentes que la leyeron (ver `media.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import lmsr
from .cloud.predicates import PREDICATES, REAL
from .errors import MarketError
from .framing import FramingExperiment, Headline
from .media import NewsCoverage
from .verdict import OUTCOMES, Verdict

KINDS = ("presente", "futuro", "sala", "simulacion")
MAX_ORDER = 10_000
MAX_HISTORY = 400  # puntos de precio guardados; al pasarse, se reduce la resolución a la mitad


@dataclass(frozen=True)
class Attempt:
    """Una consulta de resolución: qué se dijo y qué creía la sala en ese momento."""

    verdict: Verdict
    price_yes: float
    fault: str | None
    at: float


@dataclass
class Market:
    id: str
    question: str
    criteria: str
    b: float = 100.0
    kind: str = "presente"
    threshold: float = 0.5
    predicate: str | None = None
    q: list[float] = field(default_factory=lambda: [0.0, 0.0])
    status: str = "open"
    outcome: str | None = None
    history: list[float] = field(default_factory=lambda: [0.5])
    orders: int = 0
    volume: float = 0.0
    attempts: list[Attempt] = field(default_factory=list)
    census: dict[str, bool] = field(default_factory=dict)
    last_consulted_at: float = 0.0
    framing: FramingExperiment | None = None  # dos titulares y la sala dividida al azar
    news: NewsCoverage | None = None  # nació de las noticias del día

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise MarketError("tipo de pregunta inválido")
        if (self.kind == "simulacion") != (self.predicate in PREDICATES):
            raise MarketError("las preguntas de simulación necesitan un predicado conocido, y solo ellas")
        if (self.framing or self.news) and self.kind not in ("presente", "futuro"):
            raise MarketError("solo las preguntas que resuelve el oráculo pueden llevar titulares")

    @property
    def resolved_by_census(self) -> bool:
        return self.kind == "sala"

    @property
    def resolved_by_simulation(self) -> bool:
        return self.kind == "simulacion"

    @property
    def resolver(self) -> str:
        if self.predicate in REAL:
            return "infraestructura real"
        return {"sala": "censo", "simulacion": "simulación"}.get(self.kind, "oráculo")

    @property
    def max_loss(self) -> float:
        return self.b * 0.6931471805599453

    @property
    def last_attempt(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None

    def prices(self) -> dict[str, float]:
        p = lmsr.prices(self.q, self.b)
        return {"YES": p[0], "NO": p[1]}

    def ensure_open(self) -> None:
        if self.status != "open":
            raise MarketError("el mercado ya está resuelto")

    def enroll(self, who: str) -> None:
        """Asigna a la persona a un grupo: el titular del encuadre o el lado de los medios."""
        if self.status != "open":
            return
        if self.framing:
            self.framing.assign(who, self.id)
        if self.news:
            self.news.assign(who, self.id)

    def headline_for(self, who: str) -> Headline | None:
        return self.framing.headline_for(who) if self.framing else None

    def buy(self, outcome: str, spend: float, who: str | None = None) -> float:
        """Compra acciones de `outcome` por `spend` créditos. Devuelve las acciones."""
        if outcome not in OUTCOMES:
            raise MarketError("resultado inválido")
        if not 0 < spend <= MAX_ORDER:
            raise MarketError("monto inválido")
        self.ensure_open()
        i = OUTCOMES.index(outcome)
        shares = lmsr.shares_for_spend(self.q, self.b, i, spend)
        self.q[i] += shares
        self.volume += spend
        self.orders += 1
        self._remember(self.prices()["YES"])
        if self.framing and who is not None:
            self.framing.record(who, outcome, spend, self.id)
        if self.news and who is not None:
            self.news.record(who, outcome, spend, self.id)
        return shares

    def _remember(self, price: float) -> None:
        """La serie de precios no crece sin límite: al pasar de MAX_HISTORY se queda con uno de
        cada dos puntos, conservando la apertura y el último precio."""
        self.history.append(price)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[:-1:2] + [self.history[-1]]

    def answer_census(self, who: str, answer: bool) -> None:
        """Respuesta privada al censo. Una por persona e inmutable."""
        if not self.resolved_by_census:
            raise MarketError("este mercado no se resuelve por censo")
        self.ensure_open()
        if who in self.census:
            raise MarketError("ya respondiste el censo")
        self.census[who] = answer

    def record(self, verdict: Verdict, price_yes: float, fault: str | None, at: float) -> bool:
        """Registra una consulta. Devuelve True si el veredicto cerró el mercado."""
        self.attempts.append(Attempt(verdict, price_yes, fault, at))
        if verdict.decisive:
            self.status, self.outcome = "resolved", verdict.outcome
            if self.framing:
                self.framing.revealed = True
            if self.news:
                self.news.revealed = True
            return True
        return False


@dataclass
class Account:
    name: str
    balance: float
    positions: dict[str, dict[str, float]] = field(default_factory=dict)
    credential: str = ""  # hash del token de la persona; el token en claro nunca se guarda

    @staticmethod
    def normalize(name: str) -> str:
        return (name or "").strip().lower()[:24] or "anon"

    def debit(self, amount: float) -> None:
        if amount > self.balance:
            raise MarketError("saldo insuficiente")
        self.balance -= amount

    def add_shares(self, market_id: str, outcome: str, shares: float) -> None:
        pos = self.positions.setdefault(market_id, {"YES": 0.0, "NO": 0.0})
        pos[outcome] += shares

    def settle(self, market_id: str, outcome: str) -> None:
        """1 crédito por acción ganadora."""
        pos = self.positions.get(market_id)
        if pos:
            self.balance += pos[outcome]
