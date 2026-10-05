"""Mercado real: agentes que operan servicios reales de Cloud Run y venden peticiones reales.

Lo que es real aquí, y lo que no:

- **Costos:** precios de lista de Cloud Run por región, leídos del catálogo de
  Cloud Billing (`PriceTable`). No hay multiplicadores inventados.
- **Demanda:** las peticiones reales de la sala, con un tope por ciclo para que
  el costo quede acotado (`MarketBudget.max_requests`).
- **Servicio:** cada petición vendida se envía de verdad al nodo del agente
  ganador. Solo cobra si responde con 200 dentro del plazo (`sla_ms`).
- **Coaliciones:** contratos que exigen atender desde dos regiones; se ejecutan
  de verdad y se pagan solo si cumplen.
- **Evolución:** el gen `warm` decide si el agente paga una instancia mínima
  (sin arranques en frío) o no (más barato, más lento). Cambiarlo cambia la
  configuración real del servicio. La aptitud es la ganancia real medida.

El dinero es contable: nadie le paga de verdad a un agente. Pero cada costo
corresponde a algo que Google Cloud cobra de verdad, y cada ingreso a una
petición que de verdad se atendió a tiempo.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from math import ceil

from .agents import ACTIONS, QLearner
from .auction import Ask, Clearing, clear
from .coalitions import Coalition, Contract, Member, form

AGENT_PREFIX = "oraculo-agente-"
CPU = 0.25  # vCPU por instancia (mínimo que Cloud Run acepta con concurrencia 1)
MEMORY_GIB = 0.25
BILLING_QUANTUM_S = 0.1  # Cloud Run redondea cada petición hacia arriba a 100 ms


def agent_service(agent_id: str) -> str:
    return AGENT_PREFIX + agent_id


@dataclass(frozen=True)
class RegionPrice:
    """Precios de lista en USD, de una región, tal como los publica Cloud Billing."""

    cpu_s: float  # por vCPU·s atendiendo peticiones
    mem_s: float  # por GiB·s atendiendo peticiones
    idle_cpu_s: float  # por vCPU·s de instancia mínima en reposo
    idle_mem_s: float  # por GiB·s de instancia mínima en reposo


@dataclass(frozen=True)
class PriceTable:
    regions: dict[str, RegionPrice]
    per_request: float  # USD por petición (tras el nivel gratuito)
    source: str  # de dónde salieron: "cloud-billing" o "fijos de ensayo"
    fetched_at: float = 0.0

    def request_cost(self, region: str, server_ms: float | None) -> float:
        """Lo que cuesta de verdad atender una petición en esa región."""
        p = self.regions[region]
        seconds = (server_ms or 0) / 1000
        billed = max(BILLING_QUANTUM_S, ceil(seconds / BILLING_QUANTUM_S) * BILLING_QUANTUM_S)
        return billed * (CPU * p.cpu_s + MEMORY_GIB * p.mem_s) + self.per_request

    def idle_cost(self, region: str, seconds: float) -> float:
        """Lo que cuesta una instancia mínima encendida durante `seconds`."""
        p = self.regions[region]
        return seconds * (CPU * p.idle_cpu_s + MEMORY_GIB * p.idle_mem_s)


@dataclass(frozen=True)
class MarketBudget:
    """Los topes que hacen barato al mercado real."""

    max_agents: int = 4
    max_warm: int = 1  # instancias mínimas en total: lo único que cobra en reposo
    max_requests: int = 12  # peticiones reales de trabajo por ciclo
    per_agent: int = 4  # cuántas puede vender un agente por ciclo (concurrencia 1)
    sla_ms: float = 1000.0
    reservation_markup: float = 3.0  # lo máximo que paga la sala: 3× el costo real más barato
    contract_every: int = 6  # ciclos entre contratos de coalición
    generation_cycles: int = 12  # ciclos por generación


@dataclass(frozen=True)
class RealGenome:
    markup: float  # margen sobre el costo real
    cooperation: float  # probabilidad de sumarse a una coalición
    warm: bool  # pagar una instancia mínima para no tener arranques en frío

    @classmethod
    def random(cls, rng: random.Random) -> RealGenome:
        return cls(rng.uniform(0.1, 1.5), rng.random(), rng.random() < 0.3)

    def mutate(self, rng: random.Random, sigma: float = 0.15) -> RealGenome:
        return RealGenome(
            markup=min(2.0, max(0.0, self.markup + rng.gauss(0, sigma))),
            cooperation=min(1.0, max(0.0, self.cooperation + rng.gauss(0, sigma))),
            warm=(not self.warm) if rng.random() < 0.2 else self.warm,
        )

    @staticmethod
    def crossover(a: RealGenome, b: RealGenome, rng: random.Random) -> RealGenome:
        pick = lambda x, y: x if rng.random() < 0.5 else y  # noqa: E731
        return RealGenome(pick(a.markup, b.markup), pick(a.cooperation, b.cooperation), pick(a.warm, b.warm))

    def as_dict(self) -> dict:
        return {"markup": round(self.markup, 3), "cooperation": round(self.cooperation, 3), "warm": self.warm}


@dataclass
class RealAgent:
    id: str
    region: str
    genome: RealGenome
    learner: QLearner = field(default_factory=QLearner)
    offset: float = 0.0
    born: int = 1
    revenue: float = 0.0  # USD contables de la generación
    cost: float = 0.0  # USD reales de la generación
    served: int = 0
    late: int = 0  # respondió pero fuera de plazo
    failed: int = 0  # no respondió o respondió con error
    latencies: list[float] = field(default_factory=list)
    pending: tuple[tuple[int, int], int] | None = None

    @property
    def fitness(self) -> float:
        return self.revenue - self.cost

    def ask(self, prices: PriceTable) -> float:
        unit = prices.request_cost(self.region, None)
        return unit * (1 + max(0.0, self.genome.markup + self.offset))


@dataclass
class AgentState:
    """El servicio real de un agente, tal como lo ve Cloud Run."""

    id: str
    region: str
    ready: bool = False
    reconciling: bool = False
    uri: str | None = None
    warm: bool = False
    revision: str | None = None


@dataclass(frozen=True)
class WorkResult:
    """Una petición real de trabajo: lo que tardó de punta a punta y lo que midió el servidor."""

    latency_ms: float | None
    server_ms: float | None
    status: int | None


@dataclass
class Settlement:
    clearing: Clearing
    profit: dict[str, float]
    results: dict[str, list[WorkResult]]


def auction(agents: list[RealAgent], prices: PriceTable, budget: MarketBudget, demand: int) -> Clearing:
    """Reparte la demanda real (con tope) entre los agentes más baratos."""
    cheapest = min(prices.request_cost(a.region, None) for a in agents)
    asks = [Ask(a.id, a.ask(prices), budget.per_agent) for a in agents]
    return clear(asks, min(demand, budget.max_requests), cheapest * budget.reservation_markup)


def settle(agents: list[RealAgent], clearing: Clearing, results: dict[str, list[WorkResult]],
           prices: PriceTable, budget: MarketBudget, cycle_seconds: float) -> dict[str, float]:
    """Ingresos por peticiones atendidas a tiempo; costos reales de cada petición y del reposo."""
    profit = {}
    for a in agents:
        rs = results.get(a.id, [])
        answered = [r for r in rs if r.status == 200 and r.latency_ms is not None]
        ok = [r for r in answered if r.latency_ms <= budget.sla_ms]
        late = [r for r in answered if r.latency_ms > budget.sla_ms]
        revenue = len(ok) * (clearing.price or 0.0)
        cost = sum(prices.request_cost(a.region, r.server_ms) for r in rs if r.status is not None)
        if a.genome.warm:
            cost += prices.idle_cost(a.region, cycle_seconds)
        a.revenue += revenue
        a.cost += cost
        a.served += len(ok)
        a.late += len(late)
        a.failed += len(rs) - len(ok) - len(late)
        a.latencies = (a.latencies + [r.latency_ms for r in rs if r.latency_ms is not None])[-20:]
        profit[a.id] = revenue - cost
    return profit


def learn(agents: list[RealAgent], profit: dict[str, float], clearing: Clearing, rng: random.Random) -> None:
    """Q-learning con recompensas reales: la ganancia de este ciclo, en millonésimas de dólar."""
    sold_any = {a for a, q in clearing.fills.items() if q > 0}
    state_next = (1 if clearing.unmet > 0 else 0, 0)
    for a in agents:
        if a.pending:
            state, action = a.pending
            a.learner.learn(state, action, profit.get(a.id, 0.0) * 1e6, state_next)
        state = (1 if clearing.unmet > 0 else 0, 1 if a.id in sold_any else 0)
        action = a.learner.act(state, rng)
        a.offset = min(0.5, max(-0.5, a.offset + ACTIONS[action]))
        a.pending = (state, action)


def contract(agents: list[RealAgent], prices: PriceTable, budget: MarketBudget,
             rng: random.Random) -> tuple[Contract, Coalition | None, int]:
    """Un contrato que exige dos regiones: más de lo que vende un solo agente en un ciclo."""
    qty = budget.per_agent + 2
    cheapest = min(prices.request_cost(a.region, None) for a in agents)
    c = Contract(qty, qty * cheapest * budget.reservation_markup)
    willing = [Member(a.id, a.region, budget.per_agent, prices.request_cost(a.region, None))
               for a in agents if rng.random() < a.genome.cooperation]
    return c, form(c, willing), len(willing)


def evolve(agents: list[RealAgent], rng: random.Random, generation: int, budget: MarketBudget) -> None:
    """Selección y mutación entre generaciones. Respeta el tope de agentes encendidos."""
    ranked = sorted(agents, key=lambda a: a.fitness, reverse=True)
    parents = [a.genome for a in ranked[: max(1, len(ranked) // 2)]]
    for a in ranked[max(1, len(ranked) // 2):]:
        a.genome = RealGenome.crossover(rng.choice(parents), rng.choice(parents), rng).mutate(rng)
        a.learner, a.offset, a.born = QLearner(), 0.0, generation
    warm = [a for a in ranked if a.genome.warm]
    for a in warm[budget.max_warm:]:  # el presupuesto manda: los peores pierden la instancia mínima
        a.genome = replace(a.genome, warm=False)
    for a in agents:
        a.revenue = a.cost = 0.0
        a.served = a.late = a.failed = 0
