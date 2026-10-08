"""Casos de uso del mercado: operar, responder el censo y resolver."""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
import uuid
from collections.abc import Callable

from ..domain.errors import MarketError
from ..domain.framing import Framing, FramingPolicy
from ..domain.market import Account, Market
from ..domain.media import AGENTS, Article
from ..domain.verdict import CensusPolicy
from .errors import Conflict, Cooldown, NotFound, RateLimited, Unauthorized
from .limits import SlidingWindow
from .ports import FAULTS, FRAMING_FAULTS, OracleGateway, Repository, SimulationJudge
from .views import account_view, headline_view, market_view


class MarketService:
    def __init__(
        self,
        repo: Repository,
        oracle: OracleGateway,
        census: CensusPolicy | None = None,
        judge: SimulationJudge | None = None,
        framing: FramingPolicy | None = None,
        starting_balance: float = 1000.0,
        oracle_cooldown: float = 30.0,
        clock: Callable[[], float] = time.time,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
        max_accounts: int = 2000,
        entries: SlidingWindow | None = None,
        orders: SlidingWindow | None = None,
    ):
        self.repo = repo
        self.oracle = oracle
        self.census = census or CensusPolicy()
        self.judge = judge
        self.framing = framing or FramingPolicy()
        self.starting_balance = starting_balance
        self.cooldown = oracle_cooldown
        self.clock = clock
        self.new_id = new_id
        # Límites contra abuso: cuentas en memoria de una sola instancia, y ritmo de escrituras.
        self.max_accounts = max_accounts
        self.entries = entries or SlidingWindow(limit=120, window=60)  # cuentas nuevas por minuto, en total
        self.orders = orders or SlidingWindow(limit=10, window=10)  # órdenes por persona cada 10 s

    # --- lecturas ---------------------------------------------------------------
    def _market(self, market_id: str) -> Market:
        m = self.repo.get_market(market_id)
        if m is None:
            raise NotFound("mercado no encontrado")
        return m

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _authenticate(self, name: str, token: str) -> Account:
        """La persona demuestra que el nombre es suyo con el token que recibió al entrar."""
        acc = self.repo.get_account(Account.normalize(name))
        if acc is None or not token or not secrets.compare_digest(acc.credential, self._digest(token)):
            raise Unauthorized("token de usuario inválido: vuelve a entrar con otro nombre")
        return acc

    def _throttle(self, acc: Account) -> None:
        if not self.orders.allow(acc.name):
            raise RateLimited("demasiadas órdenes seguidas: espera unos segundos")

    def list(self) -> list[dict]:
        with self.repo.transaction():
            return [market_view(m) for m in self.repo.markets()]

    def view(self, market_id: str) -> dict:
        with self.repo.transaction():
            return market_view(self._market(market_id))

    def account(self, name: str, token: str) -> dict:
        """La cuenta y, por cada pregunta con titulares, el único titular que esta persona ve."""
        with self.repo.transaction():
            acc = self._authenticate(name, token)
            headlines = {m.id: headline_view(m.headline_for(acc.name))
                         for m in self.repo.markets() if m.framing and m.status == "open"}
            return account_view(acc) | {"headlines": headlines}

    def enter(self, name: str) -> dict:
        """Reserva un nombre y entrega su token. El token se muestra una sola vez."""
        name = Account.normalize(name)
        with self.repo.transaction():
            if self.repo.get_account(name) is not None:
                raise Conflict("ese nombre ya está en uso: elige otro")
            if sum(1 for _ in self.repo.accounts()) >= self.max_accounts:
                raise RateLimited("la sala está llena")
            if not self.entries.allow("global"):
                raise RateLimited("están entrando demasiadas personas a la vez: reintenta en un minuto")
            token = secrets.token_urlsafe(24)
            acc = Account(name, self.starting_balance, credential=self._digest(token))
            self.repo.add_account(acc)
            return {"name": name, "token": token} | account_view(acc)

    # --- escrituras -------------------------------------------------------------
    def create(self, question: str, criteria: str, b: float = 100.0, kind: str = "presente",
               threshold: float = 0.5, predicate: str | None = None,
               framing: Framing | None = None, topic: str = "",
               coverage: list[Article] | None = None) -> dict:
        if kind == "simulacion" and self.judge is None:
            raise MarketError("no hay simulación conectada")
        m = Market(self.new_id(), question, criteria, b=b, kind=kind, threshold=threshold,
                   predicate=predicate, framing=framing, topic=topic, coverage=list(coverage or []))
        with self.repo.transaction():
            self.repo.add_market(m)
            return market_view(m)

    def trade(self, market_id: str, user: str, token: str, outcome: str, amount: float) -> dict:
        with self.repo.transaction():
            acc = self._authenticate(user, token)
            self._throttle(acc)
            m = self._market(market_id)
            m.ensure_open()
            if amount > acc.balance:
                raise MarketError("saldo insuficiente")
            shares = m.buy(outcome, amount, acc.name)
            acc.debit(amount)
            acc.add_shares(m.id, outcome, shares)
            return {"market": market_view(m), "user": account_view(acc), "shares": shares}

    def agent_trade(self, market_id: str, agent: str, outcome: str, amount: float) -> tuple[float, float]:
        """Una orden de un agente de noticias. Devuelve (precio del SÍ antes, acciones).

        Los agentes no tienen token: su credencial vacía nunca coincide con un hash,
        así que nadie puede operar ni consultar como ellos desde la API.
        """
        if agent not in AGENTS:
            raise MarketError(f"agente desconocido: {agent}")
        with self.repo.transaction():
            acc = self.repo.get_account(agent)
            if acc is None:
                acc = Account(agent, self.starting_balance)
                self.repo.add_account(acc)
            m = self._market(market_id)
            before = m.prices()["YES"]
            amount = min(amount, acc.balance)
            if amount <= 0:
                return before, 0.0
            shares = m.buy(outcome, amount)
            acc.debit(amount)
            acc.add_shares(m.id, outcome, shares)
            return before, shares

    def answer_census(self, market_id: str, user: str, token: str, answer: bool) -> dict:
        with self.repo.transaction():
            acc = self._authenticate(user, token)
            self._throttle(acc)
            m = self._market(market_id)
            m.answer_census(acc.name, answer)
            return {"census_count": len(m.census)}

    def reveal(self, market_id: str) -> dict:
        """Muestra los dos titulares en la proyección. La sala sigue pudiendo operar."""
        with self.repo.transaction():
            m = self._market(market_id)
            if m.framing is None:
                raise MarketError("esta pregunta no tiene titulares")
            m.revealed = True
            return market_view(m)

    async def _consult(self, m: Market, fault: str | None):
        """El oráculo, y si la pregunta tiene titulares, la prueba de encuadre.

        Primero una lectura neutral. Si es decisiva, dos lecturas más, cada una con
        un titular, y `FramingPolicy` exige que coincidan. Si la neutral no decide,
        no se gasta en las otras dos.
        """
        trusted = fault in FRAMING_FAULTS
        payload_fault = None if trusted else fault
        neutral = await self.oracle.resolve(m.question, m.criteria, payload_fault)
        if m.framing is None or not neutral.decisive:
            return neutral
        news = m.framing.news(trusted)
        reads = await asyncio.gather(
            *(self.oracle.resolve(m.question, m.criteria, None, n) for n in news.values()))
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
            # Lo que la sala creía justo antes de ver la evidencia.
            belief = m.prices()["YES"]
            if m.resolved_by_census:
                verdict = self.census.tally(list(m.census.values()), m.threshold)

        if m.resolved_by_simulation:
            verdict = self.judge.judge(m.predicate)  # type: ignore[union-attr,arg-type]
        elif not m.resolved_by_census:
            # Fuera de la transacción: la llamada tarda y el mercado sigue operando.
            verdict = await self._consult(m, fault)

        with self.repo.transaction():
            if m.status != "open":  # otra resolución ganó la carrera
                return market_view(m)
            if m.record(verdict, belief, fault, self.clock()):
                m.revealed = True
                for acc in self.repo.accounts():
                    acc.settle(m.id, m.outcome)
            return market_view(m)
