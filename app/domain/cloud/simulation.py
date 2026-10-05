"""La nube simulada. Un tick hace, en orden:

1. Llega la demanda real de cada recurso (ciclo diario, tendencia, ruido, picos).
2. Cada agente elige su margen (Q-learning) y cuánta capacidad encender (autoescalado
   según Holt-Winters).
3. Una subasta de precio uniforme por recurso liquida oferta contra demanda.
4. Cada pocos ticks llega un contrato grande que solo una coalición puede cubrir.
5. Los nodos reportan latencia; el detector busca anomalías y la remediación drena
   y reemplaza nodos, o enciende el autoescalado de emergencia.
6. Al cerrar una generación, selección y mutación reemplazan a los peores.

Todo es determinista dada la semilla y la secuencia de acciones del ponente.
Ningún agente toca infraestructura real.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from math import sin, tau

from ..errors import SimulationError
from ..verdict import Verdict
from .agents import ACTIONS, Agent, Genome
from .anomaly import Detector
from .auction import Ask, clear
from .catalog import REGIONS, RESOURCES
from .coalitions import Contract, Member, form
from .evolution import mean_fitness, next_generation, replicator, shares
from .forecast import HoltWinters
from .predicates import SIMULATED as PREDICATES
from .topology import Decision, TopologyPolicy, evaluate, evolve

FAULTS = {
    "caida_nodo": "un nodo deja de responder",
    "latencia": "un nodo se vuelve lento durante 10 ticks",
    "pico_demanda": "la demanda se multiplica por 2.5 durante 6 ticks",
}

GEN_TICKS = 24
CONTRACT_EVERY = 6
PROVISION_TICKS = (3, 7)  # lo que tarda en aprovisionarse un nodo de reemplazo
BAD_REPLACEMENT = 0.2  # probabilidad de que el reemplazo herede la falla (imagen defectuosa)
LATENCY_SPIKE_TICKS = 10
SHOCK_TICKS = 6
SHOCK_FACTOR = 2.5
RESERVATION = 2.4  # lo máximo que pagan los compradores, en múltiplos del costo base
HISTORY = 120


@dataclass
class Node:
    fault: str | None = None
    fault_until: int | None = None
    drained_since: int | None = None
    ready_at: int | None = None  # cuándo estará listo el reemplazo
    detector: Detector = field(default_factory=lambda: Detector(min_jump=60))
    latency: float = 20.0


@dataclass
class Fault:
    id: int
    kind: str
    target: str | None
    tick: int
    cleared: int | None = None


@dataclass
class Incident:
    id: int
    signal: str
    target: str | None
    tick: int
    z: float
    action: str
    repaired: int | None = None
    fault: int | None = None  # None: el detector alarmó sin falla inyectada (falso positivo)


@dataclass
class GenerationStats:
    number: int
    tick: int
    shares: dict[str, float]
    fitness: dict[str, float | None]
    predicted: dict[str, float]  # lo que la dinámica del replicador espera para la siguiente
    best: str
    best_genome: dict[str, float]
    best_fitness: float


@dataclass
class ContractRecord:
    tick: int
    qty: float
    payment: float
    willing: int
    members: dict[str, float] | None  # agente → reparto de Shapley; None si no se formó


@dataclass
class ProposalRecord:
    id: int
    source: str  # "generativo" o "evolutivo"
    model: str
    tick: int
    decision: Decision
    adopted: bool
    trace: list[str]
    reasoning: str = ""


@dataclass
class Series:
    tick: list[int] = field(default_factory=list)
    demand: dict[str, list[float]] = field(default_factory=lambda: {r: [] for r in RESOURCES})
    forecast: dict[str, list[float]] = field(default_factory=lambda: {r: [] for r in RESOURCES})
    price: dict[str, list[float | None]] = field(default_factory=lambda: {r: [] for r in RESOURCES})
    unmet: list[float] = field(default_factory=list)

    def push(self, t: int, demand: dict, forecast: dict, price: dict, unmet: float) -> None:
        self.tick.append(t)
        self.unmet.append(unmet)
        for r in RESOURCES:
            self.demand[r].append(demand[r])
            self.forecast[r].append(forecast[r])
            self.price[r].append(price[r])
        if len(self.tick) > HISTORY:
            self.tick.pop(0)
            self.unmet.pop(0)
            for r in RESOURCES:
                self.demand[r].pop(0)
                self.forecast[r].pop(0)
                self.price[r].pop(0)


def _bucket(x: float) -> int:
    return 0 if x < 0.5 else 1 if x < 0.8 else 2


class Simulation:
    def __init__(self, seed: int = 7, n_agents: int = 12, capacity: float = 10.0,
                 policy: TopologyPolicy | None = None):
        self.seed = seed
        self.rng = random.Random(seed)  # noqa: S311 — reproducible a propósito; nada criptográfico
        self.policy = policy or TopologyPolicy()
        self.tick_n = 0
        regions = list(REGIONS)
        self.agents = [
            Agent(f"a{i + 1:02d}", regions[i % len(regions)],
                  {r: capacity * (0.8 + 0.4 * self.rng.random()) for r in RESOURCES},
                  Genome.random(self.rng))
            for i in range(n_agents)
        ]
        self.nodes = {a.id: Node() for a in self.agents}
        self.forecasters = {r: HoltWinters() for r in RESOURCES}
        self.base_demand = {r: sum(a.capacity[r] for a in self.agents) * 0.55 for r in RESOURCES}
        self.demand_detector = Detector(min_jump=0.3, warmup=GEN_TICKS)
        self.shock_until = -1
        self.emergency_until = -1
        self.series = Series()
        self.errors: list[tuple[float, float, float]] = []  # (real, predicho, ingenuo estacional)
        self.faults: list[Fault] = []
        self.incidents: list[Incident] = []
        self.contracts: list[ContractRecord] = []
        self.generations: list[GenerationStats] = []
        self.topology: dict[str, int] = {"us-east1": 4}  # el despliegue heredado: una sola región
        self.proposals: list[ProposalRecord] = []
        self.served = 0.0
        self.unmet = 0.0

    # --- consultas ---------------------------------------------------------------
    @property
    def generation(self) -> int:
        return len(self.generations) + 1

    def agent(self, agent_id: str) -> Agent:
        for a in self.agents:
            if a.id == agent_id:
                return a
        raise SimulationError(f"agente desconocido: {agent_id}")

    def drained(self, a: Agent) -> bool:
        return self.nodes[a.id].drained_since is not None

    # --- el tick -----------------------------------------------------------------
    def _demand(self, r: str, t: int) -> float:
        season = 1 + 0.35 * sin(tau * t / GEN_TICKS)
        trend = 1 + 0.001 * t
        shock = SHOCK_FACTOR if t < self.shock_until else 1.0
        return max(0.0, self.base_demand[r] * season * trend * self.rng.gauss(1, 0.04) * shock)

    def tick(self) -> None:
        t = self.tick_n
        live = [a for a in self.agents if not self.drained(a)]
        forecast = {r: self.forecasters[r].forecast() or self.base_demand[r] for r in RESOURCES}
        demand = {r: self._demand(r, t) for r in RESOURCES}
        installed = {r: sum(a.capacity[r] for a in live) or 1.0 for r in RESOURCES}
        scarcity = {r: forecast[r] / installed[r] for r in RESOURCES}
        mean_scarcity = sum(scarcity.values()) / len(scarcity)
        emergency = t < self.emergency_until

        # 2. Refuerzo: cada agente mueve su margen. Autoescalado: cuánto encender.
        for a in self.agents:
            if t >= a.committed_until:
                a.committed = 0.0
            state = (_bucket(mean_scarcity), a.last_sold)
            action = a.learner.act(state, self.rng)
            a.offset = min(0.5, max(-0.5, a.offset + ACTIONS[action]))
            a.pending = (state, action)
        share = max(1, len(live))
        active = {
            a.id: {r: 0.0 if self.drained(a) else a.active_capacity(r, forecast[r] / share, emergency)
                   for r in RESOURCES}
            for a in self.agents
        }

        # 3. Subasta por recurso.
        profit = dict.fromkeys(active, 0.0)
        sold = dict.fromkeys(active, 0.0)
        price: dict[str, float | None] = {}
        unmet = 0.0
        for r in RESOURCES:
            asks = [Ask(a.id, a.ask_price(r, scarcity[r]), active[a.id][r]) for a in self.agents]
            c = clear(asks, demand[r], RESOURCES[r] * RESERVATION)
            price[r] = c.price
            unmet += c.unmet
            self.served += c.served
            for a in self.agents:
                q, on, cost = c.fills.get(a.id, 0.0), active[a.id][r], a.unit_cost(r)
                profit[a.id] += q * ((c.price or 0) - cost) - max(0.0, on - q) * 0.3 * cost
                profit[a.id] -= max(0.0, a.capacity[r] - on) * 0.05 * cost
                if self.nodes[a.id].fault == "caida_nodo" and q > 0:
                    # Vendió lo que no pudo entregar: reembolso más crédito de SLA.
                    profit[a.id] -= q * (c.price or 0) + 0.5 * q * cost
                    unmet += q
                sold[a.id] += q
        self.unmet += unmet

        # 4. Contratos y coaliciones.
        if t > 0 and t % CONTRACT_EVERY == 0:
            self._contract(t, live)

        # 5. Métricas, detección y remediación.
        util = {a.id: sold[a.id] / (sum(active[a.id].values()) or 1.0) for a in self.agents}
        self._observe_nodes(t, util)
        self._observe_demand(t, demand["cpu"], forecast["cpu"])

        # Aprendizaje: el predictor ve la demanda real; los agentes, su recompensa.
        for r in RESOURCES:
            self.forecasters[r].update(demand[r])
        if t >= GEN_TICKS:
            self.errors.append((demand["cpu"], forecast["cpu"], self.series_value("cpu", GEN_TICKS)))
            self.errors = self.errors[-HISTORY:]
        nxt = _bucket(sum(self.forecasters[r].forecast() / installed[r] for r in RESOURCES) / len(RESOURCES))
        for a in self.agents:
            ratio = util[a.id]
            a.last_sold = 0 if ratio < 0.2 else 1 if ratio < 0.8 else 2
            state, action = a.pending
            a.learner.learn(state, action, profit[a.id] / 10, (nxt, a.last_sold))
            a.fitness += profit[a.id]

        self.series.push(t, demand, forecast, price, unmet)
        if t >= self.shock_until:
            self._clear_faults("pico_demanda", None, t)
        if (t + 1) % GEN_TICKS == 0:
            self._end_generation(t)
        self.tick_n += 1

    def series_value(self, r: str, lag: int) -> float:
        """Demanda real de hace `lag` ticks (para el pronóstico ingenuo estacional)."""
        d = self.series.demand[r]
        return d[-lag] if len(d) >= lag else 0.0

    def _contract(self, t: int, live: list[Agent]) -> None:
        avg = sum(a.capacity["cpu"] for a in self.agents) / len(self.agents)
        qty = round(2.2 * avg, 2)
        contract = Contract(qty, qty * RESOURCES["cpu"] * 2.0)
        willing = [
            Member(a.id, a.region, a.capacity["cpu"] * 0.5, a.unit_cost("cpu"))
            for a in live if a.committed == 0 and self.rng.random() < a.genome.cooperacion
        ]
        c = form(contract, willing)
        members = None
        if c:
            members = {m: round(v, 2) for m, v in c.shares.items()}
            for m in c.members:
                a = self.agent(m)
                a.fitness += c.shares[m]
                a.committed = c.allocation.get(m, 0.0)
                a.committed_until = t + CONTRACT_EVERY
        self.contracts.append(ContractRecord(t, qty, round(contract.payment, 2), len(willing), members))
        self.contracts = self.contracts[-40:]

    def _observe_nodes(self, t: int, util: dict[str, float]) -> None:
        for a in self.agents:
            node = self.nodes[a.id]
            if node.drained_since is not None:
                if node.ready_at is not None and t >= node.ready_at:
                    node.drained_since, node.ready_at = None, None
                    for i in self.incidents:
                        if i.target == a.id and i.repaired is None:
                            i.repaired = t
                    if node.fault == "caida_nodo" and self.rng.random() < BAD_REPLACEMENT:
                        pass  # el reemplazo salió defectuoso: la falla sigue y el detector la verá
                    else:
                        node.fault, node.fault_until = None, None
                        self._clear_faults(None, a.id, t)
                continue
            if node.fault == "latencia" and node.fault_until is not None and t >= node.fault_until:
                node.fault, node.fault_until = None, None
                self._clear_faults("latencia", a.id, t)
            latency = 20 + 25 * util[a.id] ** 2 + self.rng.gauss(0, 3)
            if node.fault == "caida_nodo":
                latency = 400 + self.rng.gauss(0, 30)
            elif node.fault == "latencia":
                latency += 150
            node.latency = latency
            z = node.detector.observe(latency)
            if z is not None:
                node.drained_since = t
                node.ready_at = t + self.rng.randint(*PROVISION_TICKS)
                self._incident(f"latencia de {a.id}", a.id, t, z, "drenar y reemplazar el nodo")

    def _observe_demand(self, t: int, real: float, predicted: float) -> None:
        z = self.demand_detector.observe((real - predicted) / max(predicted, 1.0))
        if z is not None and t >= self.emergency_until:
            self.emergency_until = t + SHOCK_TICKS
            i = self._incident("demanda sobre lo previsto", None, t, z, "autoescalado de emergencia")
            i.repaired = t + SHOCK_TICKS

    def _incident(self, signal: str, target: str | None, t: int, z: float, action: str) -> Incident:
        kind = "pico_demanda" if target is None else None
        match = next((f.id for f in self.faults if f.cleared is None and f.target == target
                      and (kind is None or f.kind == kind)
                      and not any(i.fault == f.id for i in self.incidents)), None)
        i = Incident(len(self.incidents) + 1, signal, target, t, round(z, 1), action, fault=match)
        self.incidents.append(i)
        return i

    def _clear_faults(self, kind: str | None, target: str | None, t: int) -> None:
        for f in self.faults:
            if f.cleared is None and (kind is None or f.kind == kind) and f.target == target:
                f.cleared = t

    def _end_generation(self, t: int) -> None:
        sh, fit = shares(self.agents), mean_fitness(self.agents)
        best = max(self.agents, key=lambda a: a.fitness)
        self.generations.append(GenerationStats(
            self.generation, t, sh, fit, replicator(sh, fit),
            best.id, best.genome.as_dict(), round(best.fitness, 1),
        ))
        next_generation(self.agents, self.rng, self.generation)

    # --- acciones del ponente ----------------------------------------------------
    def inject(self, kind: str, target: str | None = None) -> Fault:
        if kind not in FAULTS:
            raise SimulationError(f"falla desconocida: {kind}")
        t = self.tick_n
        if kind == "pico_demanda":
            self.shock_until = t + SHOCK_TICKS
            target = None
        else:
            healthy = [a.id for a in self.agents if not self.drained(a) and self.nodes[a.id].fault is None]
            if target is None:
                if not healthy:
                    raise SimulationError("no hay nodos sanos a los que inyectar la falla")
                target = self.rng.choice(healthy)
            elif target not in healthy:
                raise SimulationError(f"{target} no es un nodo sano")
            node = self.nodes[target]
            node.fault = kind
            node.fault_until = t + LATENCY_SPIKE_TICKS if kind == "latencia" else None
        f = Fault(len(self.faults) + 1, kind, target, t)
        self.faults.append(f)
        return f

    def review(self, source: str, model: str, raw: object, trace: list[str],
               reasoning: str = "") -> ProposalRecord:
        """Somete una propuesta de topología a la política y la adopta si mejora la actual."""
        decision = self.policy.check(raw)
        current = self.policy.check({"replicas": self.topology})
        better = decision.accepted and (
            not current.accepted or decision.score.value > current.score.value  # type: ignore[union-attr]
        )
        if better:
            self.topology = dict(decision.replicas or {})
        record = ProposalRecord(len(self.proposals) + 1, source, model, self.tick_n, decision,
                                better, trace + decision.trace +
                                (["adoptada: mejora la topología actual"] if better else
                                 ["no adoptada"] if decision.accepted else []), reasoning)
        self.proposals.append(record)
        return record

    def propose_evolutionary(self) -> ProposalRecord:
        replicas, curve = evolve(self.policy, self.rng)
        trace = [f"búsqueda evolutiva: {len(curve)} generaciones, mejor valor {curve[-1]:.2f}"]
        return self.review("evolutivo", "algoritmo genético", {"replicas": replicas}, trace)

    def brief(self) -> dict:
        """Lo que se le cuenta al modelo generativo para que proponga una topología."""
        p = self.policy
        return {
            "regiones": {r.name: {"costo": r.cost, "disponibilidad": r.availability, "latencia_ms": r.latency}
                         for r in REGIONS.values()},
            "costo_por_replica": 8.0,
            "restricciones": {
                "presupuesto": p.budget, "min_regiones": p.min_regions,
                "min_disponibilidad": p.min_availability, "max_latencia_ms": p.max_latency,
                "min_replicas": p.min_replicas, "max_por_region": p.max_per_region,
            },
            "topologia_actual": self.topology,
            "valor_actual": evaluate(self.topology).value,
        }

    # --- el juez de los mercados de la sala ----------------------------------------
    def judge(self, predicate: str) -> Verdict:
        if predicate not in PREDICATES:
            raise SimulationError(f"predicado desconocido: {predicate}")
        trace = [f"simulación: tick {self.tick_n}, generación {self.generation}"]

        def pending(why: str) -> Verdict:
            trace.append(f"{why} → UNRESOLVED")
            return Verdict("UNRESOLVED", 0.0, why, model="simulación", trace=trace)

        def decided(ok: bool, why: str) -> Verdict:
            outcome = "YES" if ok else "NO"
            trace.append(f"{why} → {outcome}")
            return Verdict(outcome, 1.0, why, model="simulación", trace=trace)

        if predicate == "cooperacion_g5":
            if len(self.generations) < 5:
                return pending(f"van {len(self.generations)} generaciones cerradas de 5")
            share = self.generations[4].shares["cooperativo"]
            return decided(share > 0.4, f"cooperativos al cerrar la generación 5: {share:.0%}")
        if predicate == "autorreparacion":
            first = next((f for f in self.faults if f.kind == "caida_nodo"), None)
            if first is None:
                return pending("todavía no hubo una caída de nodo")
            if first.cleared is None:
                return pending(f"la caída de {first.target} sigue abierta")
            took = first.cleared - first.tick
            return decided(took < 6, f"la caída de {first.target} se reparó en {took} ticks")
        first_llm = next((p for p in self.proposals if p.source == "generativo"), None)
        if first_llm is None:
            return pending("el modelo generativo todavía no propuso nada")
        accepted = first_llm.decision.accepted
        word = "aceptada" if accepted else "rechazada"
        return decided(accepted, f"la primera propuesta del modelo fue {word}")
