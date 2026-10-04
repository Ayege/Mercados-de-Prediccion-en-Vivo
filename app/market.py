"""Motor de mercados: estado en memoria + LMSR + liquidación con oráculo."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from . import lmsr
from .oracle import Oracle

OUTCOMES = ("YES", "NO")


class MarketError(Exception):
    pass


class NotFound(MarketError):
    pass


class Cooldown(MarketError):
    pass


@dataclass
class Market:
    id: str
    question: str
    criteria: str
    b: float
    q: list[float] = field(default_factory=lambda: [0.0, 0.0])
    status: str = "open"
    outcome: str | None = None
    history: list[float] = field(default_factory=lambda: [0.5])
    volume: float = 0.0
    oracle: dict | None = None
    last_oracle_at: float = 0.0

    def prices(self) -> dict[str, float]:
        p = lmsr.prices(self.q, self.b)
        return {"YES": p[0], "NO": p[1]}

    def view(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "criteria": self.criteria,
            "b": self.b,
            "q": list(self.q),
            "prices": self.prices(),
            "status": self.status,
            "outcome": self.outcome,
            "history": list(self.history),
            "volume": round(self.volume, 2),
            "oracle": self.oracle,
            "max_loss": round(self.b * 0.6931471805599453, 2),
        }


class Engine:
    def __init__(self, oracle: Oracle, starting_balance: float = 1000.0, oracle_cooldown: float = 30.0):
        self.oracle = oracle
        self.start = starting_balance
        self.cooldown = oracle_cooldown
        self.markets: dict[str, Market] = {}
        self.users: dict[str, dict] = {}
        self._lock = threading.RLock()

    # --- usuarios -----------------------------------------------------------
    def _user(self, name: str) -> dict:
        name = (name or "").strip().lower()[:24] or "anon"
        return self.users.setdefault(name, {"name": name, "balance": self.start, "positions": {}})

    def user_view(self, name: str) -> dict:
        with self._lock:
            u = self._user(name)
            return {
                "name": u["name"],
                "balance": round(u["balance"], 4),
                "positions": {k: dict(v) for k, v in u["positions"].items()},
            }

    # --- mercados -----------------------------------------------------------
    def create(self, question: str, criteria: str, b: float = 100.0) -> dict:
        with self._lock:
            m = Market(id=uuid.uuid4().hex[:8], question=question, criteria=criteria, b=b)
            self.markets[m.id] = m
            return m.view()

    def get(self, market_id: str) -> Market:
        try:
            return self.markets[market_id]
        except KeyError:
            raise NotFound("mercado no encontrado") from None

    def list(self) -> list[dict]:
        with self._lock:
            return [m.view() for m in self.markets.values()]

    def view(self, market_id: str) -> dict:
        with self._lock:
            return self.get(market_id).view()

    def trade(self, market_id: str, user: str, outcome: str, amount: float) -> dict:
        if outcome not in OUTCOMES:
            raise MarketError("resultado inválido")
        if not 0 < amount <= 10_000:
            raise MarketError("monto inválido")
        with self._lock:
            m = self.get(market_id)
            if m.status != "open":
                raise MarketError("el mercado ya está resuelto")
            u = self._user(user)
            if amount > u["balance"]:
                raise MarketError("saldo insuficiente")
            i = OUTCOMES.index(outcome)
            shares = lmsr.shares_for_spend(m.q, m.b, i, amount)
            m.q[i] += shares
            u["balance"] -= amount
            pos = u["positions"].setdefault(market_id, {"YES": 0.0, "NO": 0.0})
            pos[outcome] += shares
            m.volume += amount
            m.history.append(m.prices()["YES"])
            return {"market": m.view(), "user": self.user_view(u["name"]), "shares": shares}

    async def resolve(self, market_id: str) -> dict:
        with self._lock:
            m = self.get(market_id)
            if m.status != "open":
                raise MarketError("el mercado ya está resuelto")
            wait = self.cooldown - (time.time() - m.last_oracle_at)
            if wait > 0:
                raise Cooldown(f"espera {int(wait) + 1} s antes de volver a consultar al oráculo")
            m.last_oracle_at = time.time()
        verdict = await self.oracle.resolve(m.question, m.criteria)
        with self._lock:
            if m.status != "open":  # otra resolución ganó la carrera
                return m.view()
            m.oracle = verdict.as_dict()
            if verdict.outcome in OUTCOMES:
                m.status, m.outcome = "resolved", verdict.outcome
                for u in self.users.values():
                    pos = u["positions"].get(m.id)
                    if pos:
                        u["balance"] += pos[verdict.outcome]  # 1 crédito por acción ganadora
            return m.view()
