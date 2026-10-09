"""Casos de uso del mercado: crear preguntas, operar, responder el censo y revelar titulares.

La identidad de la audiencia vive en `Accounts` y la resolución en `Resolver`.
`MarketService` las compone para que la API tenga un solo punto de entrada.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from ..domain.cloud.predicates import SIMULATED
from ..domain.errors import MarketError
from ..domain.framing import Framing, FramingExperiment, FramingPolicy
from ..domain.market import Account, Market
from ..domain.media import AGENTS, Article, NewsCoverage
from ..domain.verdict import CensusPolicy
from .accounts import Accounts
from .errors import require_market
from .limits import SlidingWindow
from .ports import OracleGateway, Repository, SimulationJudge
from .resolution import Resolver
from .views import account_view, market_summary, market_view


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
        room_code: str = "",
        only_real: bool = False,
    ):
        self.repo = repo
        self.only_real = only_real
        self.new_id = new_id
        self.starting_balance = starting_balance
        self.accounts = Accounts(repo, starting_balance, max_accounts, entries, orders, room_code)
        self.resolver = Resolver(repo, oracle, census, judge, framing, oracle_cooldown, clock)

    # --- composición -------------------------------------------------------------
    @property
    def oracle(self) -> OracleGateway:
        return self.resolver.oracle

    @oracle.setter
    def oracle(self, value: OracleGateway) -> None:
        self.resolver.oracle = value

    @property
    def judge(self) -> SimulationJudge | None:
        return self.resolver.judge

    @property
    def room_code(self) -> str:
        return self.accounts.room_code

    def enter(self, name: str, code: str = "") -> dict:
        return self.accounts.enter(name, code)

    def account(self, name: str, token: str) -> dict:
        return self.accounts.view(name, token)

    async def resolve(self, market_id: str, fault: str | None = None) -> dict:
        return await self.resolver.resolve(market_id, fault)

    # --- foto del estado ------------------------------------------------------------
    def snapshot(self) -> dict:
        """Mercados, cuentas (con el hash de cada token) y el código de sala: con eso, los
        móviles siguen funcionando después de que la API despierte."""
        return {"markets": list(self.repo.markets()), "accounts": list(self.repo.accounts()),
                "room_code": self.accounts.room_code}

    def restore(self, state: dict) -> None:
        self.repo.replace(state["markets"], state["accounts"])
        self.accounts.room_code = state["room_code"]

    # --- lecturas ---------------------------------------------------------------
    def list(self, summary: bool = False) -> list[dict]:
        view = market_summary if summary else market_view
        with self.repo.transaction():
            return [view(m) for m in self.repo.markets()]

    def view(self, market_id: str) -> dict:
        with self.repo.transaction():
            return market_view(require_market(self.repo, market_id))

    # --- escrituras -------------------------------------------------------------
    def create(self, question: str, criteria: str, b: float = 100.0, kind: str = "presente",
               threshold: float = 0.5, predicate: str | None = None,
               framing: Framing | None = None, topic: str = "",
               coverage: list[Article] | None = None) -> dict:
        if kind == "simulacion" and self.judge is None:
            raise MarketError("no hay simulación conectada")
        if self.only_real and predicate in SIMULATED:
            raise MarketError("aquí todo es real: esa pregunta la resolvería el laboratorio simulado")
        if self.only_real and framing and not (framing.pro_si.url and framing.pro_no.url):
            raise MarketError("aquí todo es real: cada titular necesita el enlace https donde lo "
                              "publicó el medio")
        m = Market(self.new_id(), question, criteria, b=b, kind=kind, threshold=threshold,
                   predicate=predicate,
                   framing=FramingExperiment(framing) if framing else None,
                   news=NewsCoverage(topic, list(coverage)) if coverage else None)
        with self.repo.transaction():
            self.repo.add_market(m)
            if m.framing:  # quien ya estaba en la sala recibe su grupo ahora, no al leer
                for acc in self.repo.accounts():
                    if acc.name not in AGENTS:
                        m.enroll(acc.name)
            return market_view(m)

    def trade(self, market_id: str, user: str, token: str, outcome: str, amount: float) -> dict:
        with self.repo.transaction():
            acc = self.accounts.authenticate(user, token)
            self.accounts.throttle(acc)
            m = require_market(self.repo, market_id)
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
            m = require_market(self.repo, market_id)
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
            acc = self.accounts.authenticate(user, token)
            self.accounts.throttle(acc)
            m = require_market(self.repo, market_id)
            m.answer_census(acc.name, answer)
            return {"census_count": len(m.census)}

    def reveal(self, market_id: str) -> dict:
        """Muestra los dos titulares en la proyección. La sala sigue pudiendo operar."""
        with self.repo.transaction():
            m = require_market(self.repo, market_id)
            if m.framing is None:
                raise MarketError("esta pregunta no tiene titulares")
            m.framing.revealed = True
            return market_view(m)
