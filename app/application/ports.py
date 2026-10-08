"""Puertos: lo que los casos de uso necesitan del mundo exterior, sin saber quién lo da."""
from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractContextManager
from typing import Protocol

from ..domain.cloud.infra import NodeState, Probe
from ..domain.cloud.real_market import AgentState, PriceTable, WorkResult
from ..domain.cloud.topology import Draft
from ..domain.framing import News
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
# Fallos de encuadre: no corrompen la respuesta, cambian cómo le llega la noticia al
# modelo. Solo aplican a preguntas con titulares; los maneja el caso de uso.
FRAMING_FAULTS = {
    "noticia_como_verdad": "el pipeline le pasa el titular al modelo como un hecho verificado",
}


class OracleGateway(Protocol):
    """Un componente no confiable que propone un veredicto con evidencia.

    Contrato: nunca lanza. Ante cualquier fallo devuelve un Verdict UNRESOLVED.
    Si recibe `news`, se la muestra al modelo: como dato no confiable o, si
    `news.trusted`, como el hecho verificado que un pipeline descuidado le pasaría.
    """

    name: str
    model: str

    async def resolve(self, question: str, criteria: str, fault: str | None = None,
                      news: News | None = None) -> Verdict: ...


class Repository(Protocol):
    """Estado de mercados y cuentas. `transaction()` hace atómica una operación."""

    def transaction(self) -> AbstractContextManager[None]: ...

    def add_market(self, market: Market) -> None: ...

    def get_market(self, market_id: str) -> Market | None: ...

    def markets(self) -> Iterable[Market]: ...

    def get_account(self, name: str) -> Account | None: ...

    def add_account(self, account: Account) -> None: ...

    def accounts(self) -> Iterable[Account]: ...


class SimulationJudge(Protocol):
    """Resuelve las preguntas `simulacion` a partir del estado de la nube simulada."""

    def judge(self, predicate: str) -> Verdict: ...


class TopologyGenerator(Protocol):
    """Un modelo generativo que propone topologías. Tan poco confiable como el oráculo.

    Contrato: nunca lanza. Si falla, devuelve un Draft sin propuesta y con la traza.
    """

    name: str
    model: str

    async def propose(self, brief: dict) -> Draft: ...


class NodeGateway(Protocol):
    """Servicios `oraculo-nodo-<región>` en una nube, real o de ensayo.

    Contrato: solo toca servicios con ese prefijo. Las escrituras pueden lanzar;
    el controlador las registra como fallidas y sigue.
    """

    name: str

    async def list(self) -> dict[str, NodeState]: ...

    async def create(self, region: str, min_instances: int, max_instances: int) -> str: ...

    async def scale(self, region: str, min_instances: int, max_instances: int) -> str: ...

    async def set_fault(self, region: str, fault: str | None) -> str: ...

    async def delete(self, region: str) -> str: ...

    async def probe(self, state: NodeState) -> Probe: ...


class PriceCatalog(Protocol):
    """Precios de lista de Cloud Run por región. Contrato: lanza si no puede obtenerlos."""

    async def get(self) -> PriceTable: ...


class AgentGateway(Protocol):
    """Servicios `oraculo-agente-<id>`, uno por agente del mercado real.

    Contrato: solo toca servicios con ese prefijo y la etiqueta de la demo.
    """

    name: str

    async def list_agents(self) -> dict[str, AgentState]: ...

    async def ensure_agent(self, agent_id: str, region: str, warm: bool) -> str: ...

    async def delete_agent(self, agent_id: str, region: str) -> str: ...

    async def work(self, state: AgentState, n: int) -> list[WorkResult]: ...
