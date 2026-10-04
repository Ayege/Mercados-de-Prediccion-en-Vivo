"""Puertos: lo que los casos de uso necesitan del mundo exterior, sin saber quién lo da."""
from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractContextManager
from typing import Protocol

from ..domain.market import Account, Market
from ..domain.verdict import Verdict

# Fallos que el ponente puede pedirle a cualquier oráculo para ensayar la política
# en vivo. Forman parte del contrato del puerto: todo adaptador debe soportarlos.
FAULTS = {
    "baja_confianza": "el modelo responde, pero con confianza 0.55",
    "un_dominio": "el grounding solo trae fuentes de un dominio",
    "json_malformado": "el texto del modelo no es JSON",
    "red_caida": "la llamada al modelo falla",
}


class OracleGateway(Protocol):
    """Un componente no confiable que propone un veredicto con evidencia.

    Contrato: nunca lanza. Ante cualquier fallo devuelve un Verdict UNRESOLVED.
    """

    name: str
    model: str

    async def resolve(self, question: str, criteria: str, fault: str | None = None) -> Verdict: ...


class Repository(Protocol):
    """Estado de mercados y cuentas. `transaction()` hace atómica una operación."""

    def transaction(self) -> AbstractContextManager[None]: ...

    def add_market(self, market: Market) -> None: ...

    def get_market(self, market_id: str) -> Market | None: ...

    def markets(self) -> Iterable[Market]: ...

    def get_account(self, name: str) -> Account | None: ...

    def add_account(self, account: Account) -> None: ...

    def accounts(self) -> Iterable[Account]: ...
