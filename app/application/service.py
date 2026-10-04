"""Casos de uso del mercado: operar, responder el censo y resolver."""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from ..domain.errors import MarketError
from ..domain.market import Account, Market
from ..domain.verdict import CensusPolicy
from .errors import Cooldown, NotFound
from .ports import FAULTS, OracleGateway, Repository
from .views import account_view, market_view


class MarketService:
    def __init__(
        self,
        repo: Repository,
        oracle: OracleGateway,
        census: CensusPolicy | None = None,
        starting_balance: float = 1000.0,
        oracle_cooldown: float = 30.0,
        clock: Callable[[], float] = time.time,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
    ):
        self.repo = repo
        self.oracle = oracle
        self.census = census or CensusPolicy()
        self.starting_balance = starting_balance
        self.cooldown = oracle_cooldown
        self.clock = clock
        self.new_id = new_id

    # --- lecturas ---------------------------------------------------------------
    def _market(self, market_id: str) -> Market:
        m = self.repo.get_market(market_id)
        if m is None:
            raise NotFound("mercado no encontrado")
        return m

    def _account(self, name: str) -> Account:
        name = Account.normalize(name)
        acc = self.repo.get_account(name)
        if acc is None:
            acc = Account(name, self.starting_balance)
            self.repo.add_account(acc)
        return acc

    def list(self) -> list[dict]:
        with self.repo.transaction():
            return [market_view(m) for m in self.repo.markets()]

    def view(self, market_id: str) -> dict:
        with self.repo.transaction():
            return market_view(self._market(market_id))

    def account(self, name: str) -> dict:
        with self.repo.transaction():
            return account_view(self._account(name))

    # --- escrituras -------------------------------------------------------------
    def create(self, question: str, criteria: str, b: float = 100.0,
               kind: str = "presente", threshold: float = 0.5) -> dict:
        m = Market(self.new_id(), question, criteria, b=b, kind=kind, threshold=threshold)
        with self.repo.transaction():
            self.repo.add_market(m)
            return market_view(m)

    def trade(self, market_id: str, user: str, outcome: str, amount: float) -> dict:
        with self.repo.transaction():
            m = self._market(market_id)
            m.ensure_open()
            acc = self._account(user)
            if amount > acc.balance:
                raise MarketError("saldo insuficiente")
            shares = m.buy(outcome, amount)
            acc.debit(amount)
            acc.add_shares(m.id, outcome, shares)
            return {"market": market_view(m), "user": account_view(acc), "shares": shares}

    def answer_census(self, market_id: str, user: str, answer: bool) -> dict:
        with self.repo.transaction():
            m = self._market(market_id)
            m.answer_census(self._account(user).name, answer)
            return {"census_count": len(m.census)}

    async def resolve(self, market_id: str, fault: str | None = None) -> dict:
        if fault is not None and fault not in FAULTS:
            raise MarketError(f"fallo desconocido: {fault}")
        with self.repo.transaction():
            m = self._market(market_id)
            m.ensure_open()
            now = self.clock()
            wait = self.cooldown - (now - m.last_consulted_at)
            if not m.resolved_by_census and wait > 0:
                raise Cooldown(f"espera {int(wait) + 1} s antes de volver a consultar al oráculo")
            m.last_consulted_at = now
            # Lo que la sala creía justo antes de ver la evidencia.
            belief = m.prices()["YES"]
            if m.resolved_by_census:
                verdict = self.census.tally(list(m.census.values()), m.threshold)

        if not m.resolved_by_census:
            # Fuera de la transacción: la llamada tarda y el mercado sigue operando.
            verdict = await self.oracle.resolve(m.question, m.criteria, fault)

        with self.repo.transaction():
            if m.status != "open":  # otra resolución ganó la carrera
                return market_view(m)
            if m.record(verdict, belief, fault, self.clock()):
                for acc in self.repo.accounts():
                    acc.settle(m.id, m.outcome)
            return market_view(m)
