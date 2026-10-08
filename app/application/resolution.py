"""Resolver una pregunta: censo, simulación, infraestructura real u oráculo.

El oráculo es un componente no confiable. En preguntas con encuadre se lo
consulta tres veces (sin titular y con cada uno) y `FramingPolicy` exige que
coincidan. La llamada al modelo ocurre fuera de la transacción: tarda, y el
mercado sigue operando mientras tanto.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from ..domain.errors import MarketError
from ..domain.framing import FramingPolicy
from ..domain.market import Market
from ..domain.verdict import CensusPolicy, Verdict
from .errors import Cooldown, NotFound
from .ports import FAULTS, FRAMING_FAULTS, OracleGateway, OracleQuery, Repository, SimulationJudge
from .views import market_view


class Resolver:
    def __init__(self, repo: Repository, oracle: OracleGateway, census: CensusPolicy | None = None,
                 judge: SimulationJudge | None = None, framing: FramingPolicy | None = None,
                 cooldown: float = 30.0, clock: Callable[[], float] = time.time):
        self.repo = repo
        self.oracle = oracle
        self.census = census or CensusPolicy()
        self.judge = judge
        self.framing = framing or FramingPolicy()
        self.cooldown = cooldown
        self.clock = clock

    def _market(self, market_id: str) -> Market:
        m = self.repo.get_market(market_id)
        if m is None:
            raise NotFound("mercado no encontrado")
        return m

    async def _consult(self, m: Market, fault: str | None) -> Verdict:
        """Primero una lectura neutral. Si es decisiva y hay titulares, dos lecturas más.
        Si la neutral no decide, no se gasta en las otras dos."""
        trusted = fault in FRAMING_FAULTS
        neutral = await self.oracle.resolve(OracleQuery(m.question, m.criteria, None if trusted else fault))
        if m.framing is None or not neutral.decisive:
            return neutral
        news = m.framing.news(trusted)
        reads = await asyncio.gather(
            *(self.oracle.resolve(OracleQuery(m.question, m.criteria, news=n)) for n in news.values()))
        return self.framing.apply(neutral, dict(zip(news, reads, strict=True)))

    async def resolve(self, market_id: str, fault: str | None = None) -> dict:
        if fault is not None and fault not in FAULTS and fault not in FRAMING_FAULTS:
            raise MarketError(f"fallo desconocido: {fault}")
        with self.repo.transaction():
            m = self._market(market_id)
            m.ensure_open()
            if fault in FRAMING_FAULTS and m.framing is None:
                raise MarketError("ese fallo solo aplica a preguntas con titulares")
            now = self.clock()
            wait = self.cooldown - (now - m.last_consulted_at)
            if m.kind in ("presente", "futuro") and wait > 0:
                raise Cooldown(f"espera {int(wait) + 1} s antes de volver a consultar al oráculo")
            m.last_consulted_at = now
            belief = m.prices()["YES"]  # lo que la sala creía justo antes de ver la evidencia
            if m.resolved_by_census:
                verdict = self.census.tally(list(m.census.values()), m.threshold)

        if m.resolved_by_simulation:
            if self.judge is None:
                raise MarketError("no hay simulación conectada")
            verdict = self.judge.judge(m.predicate or "")
        elif not m.resolved_by_census:
            verdict = await self._consult(m, fault)

        with self.repo.transaction():
            if m.status != "open":  # otra resolución ganó la carrera
                return market_view(m)
            if m.record(verdict, belief, fault, self.clock()):
                for acc in self.repo.accounts():
                    acc.settle(m.id, m.outcome)
            return market_view(m)
