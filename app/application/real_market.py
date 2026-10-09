"""Controlador del mercado real: agentes con servicios reales que venden peticiones reales.

Corre dentro del ciclo de `InfraController` y comparte sus frenos: solo actúa con
la actuación activa, y «Apagar todo» y la vigilia borran también los agentes.
Cada ciclo:

1. Refresca los precios reales (Cloud Billing, cacheados una hora).
2. Observa los servicios `oraculo-agente-*` y corrige su configuración si el
   genoma cambió (el gen `warm` es una instancia mínima real).
3. Subasta la demanda real de la sala, con tope, entre los agentes listos.
4. Envía de verdad cada petición vendida al nodo del ganador y mide la respuesta.
5. Liquida: ingreso solo por lo atendido a tiempo; costo real de cada petición y
   de cada segundo de instancia mínima.
6. Cada pocos ciclos, un contrato que exige dos regiones: coalición, reparto por
   Shapley, ejecución real; se paga solo si se cumple.
7. Al cerrar una generación, selección y mutación con la ganancia real como aptitud.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..domain.cloud.real_market import (
    AgentState,
    MarketBudget,
    PriceTable,
    RealAgent,
    RealGenome,
    WorkResult,
    auction,
    contract,
    evolve,
    learn,
    settle,
)
from ..domain.verdict import Verdict
from .ports import AgentGateway, PriceCatalog

log = logging.getLogger("oraculo.mercado")
REGIONS = ("us-east1", "us-central1", "europe-west1", "southamerica-east1", "northamerica-northeast1")
COOPERATION_GENERATION = 3  # cada generación son 12 ciclos de 10 s: se resuelve en unos 6 minutos


@dataclass
class Trade:
    at: float
    demand: int
    price: float | None
    fills: dict[str, int]
    unmet: float
    results: dict[str, dict]


@dataclass
class ContractRun:
    at: float
    qty: int
    payment: float
    willing: int
    shares: dict[str, float] | None
    regions: list[str] = field(default_factory=list)
    fulfilled: bool | None = None
    detail: str = ""


@dataclass
class Generation:
    number: int
    at: float
    agents: list[dict]
    warm_share: float
    best: str


class RealMarket:
    def __init__(
        self,
        gateway: AgentGateway,
        prices: PriceCatalog,
        budget: MarketBudget | None = None,
        seed: int = 5,
        cycle_seconds: float = 10.0,
        clock: Callable[[], float] = time.time,
    ):
        self.gateway = gateway
        self.prices = prices
        self.budget = budget or MarketBudget()
        self.cycle_seconds = cycle_seconds
        self.clock = clock
        self.rng = random.Random(seed)  # noqa: S311 — decisiones de agentes, nada criptográfico
        self.agents = [
            RealAgent(f"r{i + 1}", REGIONS[i % len(REGIONS)], RealGenome.random(self.rng))
            for i in range(self.budget.max_agents)
        ]
        self.table: PriceTable | None = None
        self.actual: dict[str, AgentState] = {}
        self.cycles = 0
        self.generation = 1
        self.trades: list[Trade] = []
        self.contracts: list[ContractRun] = []
        self.generations: list[Generation] = []
        self.notes: list[str] = []
        self.error = ""
        self.spend = 0.0  # USD reales gastados por el mercado (precios de lista)
        self.initial_cooperation = self._mean_cooperation(a.genome.as_dict() for a in self.agents)

    # --- ciclo ------------------------------------------------------------------
    async def cycle(self, demand: int, active: bool) -> None:
        now = self.clock()
        self.notes = []
        try:
            self.table = await self.prices.get()
            self.actual = await self.gateway.list_agents()
        except Exception as exc:  # noqa: BLE001 — sin precios o sin estado real, no se opera
            self.error = f"{type(exc).__name__}: {exc}"[:300]
            return
        self.error = ""
        if not active:
            self.notes.append("actuación en pausa: los agentes no operan")
            return
        await self._reconcile()

        ready = [
            a
            for a in self.agents
            if (st := self.actual.get(a.id)) and st.ready and not st.reconciling and st.warm == a.genome.warm
        ]
        if not ready:
            self.notes.append("ningún agente tiene su servicio listo todavía")
            return
        before = sum(a.cost for a in self.agents)
        clearing = auction(ready, self.table, self.budget, demand)
        results: dict[str, list[WorkResult]] = {}
        for agent_id, qty in clearing.fills.items():
            n = int(round(qty))
            if n:
                results[agent_id] = await self.gateway.work(self.actual[agent_id], n)
        profit = settle(self.agents, clearing, results, self.table, self.budget, self.cycle_seconds)
        learn(ready, profit, clearing, self.rng)
        self.trades.append(
            Trade(
                now,
                demand,
                clearing.price,
                {k: int(round(v)) for k, v in clearing.fills.items()},
                clearing.unmet,
                {k: self._summary(v) for k, v in results.items()},
            )
        )
        self.trades = self.trades[-30:]

        self.cycles += 1
        if self.cycles % self.budget.contract_every == 0 and len(ready) >= 2:
            await self._contract(ready, now)
        self.spend += sum(a.cost for a in self.agents) - before
        if self.cycles % self.budget.generation_cycles == 0:
            self._close_generation(now)

    async def _reconcile(self) -> None:
        """Que cada agente tenga su servicio, con la instancia mínima que dice su genoma.
        Como mucho dos llamadas de escritura por ciclo, y nunca sobre un servicio que se está aplicando."""
        writes = 0
        for a in self.agents:
            st = self.actual.get(a.id)
            if writes >= 2 or (st and (st.reconciling or st.warm == a.genome.warm)):
                continue
            try:
                result = await self.gateway.ensure_agent(a.id, a.region, a.genome.warm)
                self.notes.append(
                    f"{a.id}: {'crear' if st is None else 'cambiar instancia mínima'} → {result}"
                )
            except Exception as exc:  # noqa: BLE001 — se reintenta en el siguiente ciclo
                self.notes.append(f"{a.id}: error al configurar su servicio ({type(exc).__name__})")
            writes += 1

    async def _contract(self, ready: list[RealAgent], now: float) -> None:
        c, coalition, willing = contract(ready, self.table, self.budget, self.rng)
        run = ContractRun(now, int(c.qty), c.payment, willing, None)
        self.contracts.append(run)
        self.contracts = self.contracts[-10:]
        if coalition is None:
            run.detail = "nadie formó una coalición que cubra dos regiones"
            return
        run.shares = {k: round(v, 9) for k, v in coalition.shares.items()}
        index = {a.id: a for a in ready}
        served, regions = 0, set()
        for agent_id, qty in coalition.allocation.items():
            a = index[agent_id]
            rs = await self.gateway.work(self.actual[agent_id], int(round(qty)))
            ok = [r for r in rs if r.status == 200 and (r.latency_ms or 1e9) <= self.budget.sla_ms]
            served += len(ok)
            if ok:
                regions.add(a.region)
            a.cost += sum(self.table.request_cost(a.region, r.server_ms) for r in rs if r.status is not None)
        run.regions = sorted(regions)
        run.fulfilled = served >= c.qty and len(regions) >= 2
        if run.fulfilled:
            for agent_id, share in coalition.shares.items():
                index[agent_id].revenue += share + self.table.request_cost(
                    index[agent_id].region, None
                ) * coalition.allocation.get(agent_id, 0)
            run.detail = f"cumplido: {served} de {int(c.qty)} a tiempo desde {', '.join(run.regions)}"
        else:
            run.detail = (
                f"incumplido: {served} de {int(c.qty)} a tiempo, {len(regions)} región(es); no se paga"
            )

    def _close_generation(self, now: float) -> None:
        warm = sum(a.genome.warm for a in self.agents) / len(self.agents)
        best = max(self.agents, key=lambda a: a.fitness)
        self.generations.append(
            Generation(self.generation, now, [self._agent_view(a) for a in self.agents], warm, best.id)
        )
        self.generation += 1
        evolve(self.agents, self.rng, self.generation, self.budget)

    # --- foto del estado ---------------------------------------------------------
    PERSISTED = ("agents", "rng", "cycles", "generation", "trades", "contracts", "generations", "spend",
                 "initial_cooperation")

    def snapshot(self) -> dict:
        """La evolución y sus cuentas. Los servicios reales no: se vuelven a leer de Cloud Run."""
        return {k: getattr(self, k) for k in self.PERSISTED}

    def restore(self, state: dict) -> None:
        for k in self.PERSISTED:
            setattr(self, k, state[k])

    @staticmethod
    def _mean_cooperation(genomes) -> float:
        values = [g["cooperation"] for g in genomes]
        return sum(values) / len(values)

    def judge_cooperation(self, generation: int = COOPERATION_GENERATION) -> Verdict:
        """¿La evolución con ganancia real premió cooperar? Compara los genomas que vivieron la
        generación pedida con los del arranque. Hasta que esa generación cierre, no se resuelve."""
        trace = [f"mercado real: {len(self.agents)} agentes, cooperación media al empezar "
                 f"{self.initial_cooperation:.2f}"]
        closed = next((g for g in self.generations if g.number == generation), None)
        if closed is None:
            why = f"la generación {generation} todavía no cerró (va la {self.generation})"
            trace.append(f"{why} → UNRESOLVED")
            return Verdict("UNRESOLVED", 0.0, why, model="mercado real", trace=trace)
        now = self._mean_cooperation(a["genome"] for a in closed.agents)
        outcome = "YES" if now > self.initial_cooperation else "NO"
        why = (f"al cerrar la generación {generation}, cooperación media {now:.2f} "
               f"contra {self.initial_cooperation:.2f} al empezar")
        trace.append(f"{why} → {outcome}")
        return Verdict(outcome, 1.0, why, model="mercado real", trace=trace)

    async def shutdown(self) -> list[str]:
        """Borra los servicios de todos los agentes. Siempre permitido."""
        done = []
        try:
            actual = await self.gateway.list_agents()
        except Exception as exc:  # noqa: BLE001
            return [f"no se pudo listar los agentes ({type(exc).__name__})"]
        for agent_id, st in actual.items():
            try:
                done.append(f"{agent_id}: {await self.gateway.delete_agent(agent_id, st.region)}")
            except Exception as exc:  # noqa: BLE001
                done.append(f"{agent_id}: error al borrar ({type(exc).__name__})")
        return done

    async def exists(self) -> bool:
        return bool(await self.gateway.list_agents())

    # --- vista ------------------------------------------------------------------
    @staticmethod
    def _summary(rs: list[WorkResult]) -> dict:
        lat = sorted(r.latency_ms for r in rs if r.latency_ms is not None)
        return {
            "n": len(rs),
            "ok": sum(r.status == 200 for r in rs),
            "p50_ms": round(lat[len(lat) // 2]) if lat else None,
            "max_ms": round(lat[-1]) if lat else None,
        }

    def _agent_view(self, a: RealAgent) -> dict:
        st = self.actual.get(a.id)
        lat = sorted(a.latencies)
        return {
            "id": a.id,
            "region": a.region,
            "born": a.born,
            "genome": a.genome.as_dict(),
            "markup": round(max(0.0, a.genome.markup + a.offset), 2),
            "ask_usd": a.ask(self.table) if self.table else None,
            "served": a.served,
            "late": a.late,
            "failed": a.failed,
            "p50_ms": round(lat[len(lat) // 2]) if lat else None,
            "revenue_usd": a.revenue,
            "cost_usd": a.cost,
            "profit_usd": a.fitness,
            "service": None
            if st is None
            else {"ready": st.ready, "reconciling": st.reconciling, "warm": st.warm, "revision": st.revision},
        }

    def view(self, detailed: bool = True) -> dict:
        t = self.table
        return {
            "budget": vars(self.budget),
            "prices": None
            if t is None
            else {
                "source": t.source,
                "fetched_at": t.fetched_at,
                "per_request": t.per_request,
                "request_cost": {r: t.request_cost(r, None) for r in t.regions},
                "warm_hour": {r: t.idle_cost(r, 3600) for r in t.regions},
            },
            "generation": self.generation,
            "cycles": self.cycles,
            "spend_usd": self.spend,
            "error": self.error
            if detailed
            else ("error (los detalles solo los ve el ponente)" if self.error else ""),
            "notes": list(self.notes),
            "agents": [
                self._agent_view(a) for a in sorted(self.agents, key=lambda a: a.fitness, reverse=True)
            ],
            "trades": [vars(x) for x in self.trades[-10:]][::-1],
            "contracts": [vars(x) for x in self.contracts][::-1],
            "generations": [vars(g) for g in self.generations][-6:],
        }
