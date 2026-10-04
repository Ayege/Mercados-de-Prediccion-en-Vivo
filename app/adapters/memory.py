"""Repositorio en memoria. El mercado dura 40 minutos y corre en una sola instancia.

Si tuviera que sobrevivir a un reinicio, este es el único archivo que cambia:
un adaptador de Firestore que implemente el mismo puerto `Repository`.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from ..domain.market import Account, Market


class InMemoryRepository:
    def __init__(self) -> None:
        self._markets: dict[str, Market] = {}
        self._accounts: dict[str, Account] = {}
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            yield

    def add_market(self, market: Market) -> None:
        self._markets[market.id] = market

    def get_market(self, market_id: str) -> Market | None:
        return self._markets.get(market_id)

    def markets(self) -> list[Market]:
        return list(self._markets.values())

    def get_account(self, name: str) -> Account | None:
        return self._accounts.get(name)

    def add_account(self, account: Account) -> None:
        self._accounts[account.name] = account

    def accounts(self) -> list[Account]:
        return list(self._accounts.values())
