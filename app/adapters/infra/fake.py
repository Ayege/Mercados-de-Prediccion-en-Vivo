"""Nube de ensayo en memoria: se comporta como Cloud Run sin costar nada.

Los cambios tardan un par de ciclos en aplicarse (como `reconciling`), la
latencia tiene ruido y las fallas se ven en el sondeo igual que en la real.
"""
from __future__ import annotations

import random
from dataclasses import replace

from ...domain.cloud.catalog import REGIONS
from ...domain.cloud.infra import NODE_FAULTS, NodeState, Probe
from ...domain.cloud.real_market import AgentState, WorkResult


class FakeNodeGateway:
    name = "ensayo"

    def __init__(self, seed: int = 11, settle: int = 2):
        self.rng = random.Random(seed)  # noqa: S311 — ruido de una nube de ensayo
        self.settle = settle
        self.nodes: dict[str, NodeState] = {}
        self.pending: dict[str, int] = {}
        self.calls: list[tuple[str, str]] = []
        self.agents: dict[str, AgentState] = {}
        self.agent_pending: dict[str, int] = {}
        self.cold: dict[str, bool] = {}  # sin instancia mínima, la primera petición arranca en frío

    def _check(self, region: str) -> None:
        if region not in REGIONS:
            raise ValueError(f"región desconocida: {region}")

    def _touch(self, region: str) -> None:
        n = self.nodes[region]
        n.revision = f"r{int((n.revision or 'r0')[1:]) + 1}"
        self.pending[region] = self.settle

    async def list(self) -> dict[str, NodeState]:
        for region, n in self.nodes.items():
            left = self.pending.get(region, 0)
            n.reconciling = left > 0
            n.ready = not n.reconciling
            self.pending[region] = max(0, left - 1)
        return {r: replace(n) for r, n in self.nodes.items()}

    async def create(self, region: str, min_instances: int, max_instances: int) -> str:
        self._check(region)
        self.calls.append(("crear", region))
        self.nodes[region] = NodeState(region, uri=f"https://ensayo/{region}",
                                       min_instances=min_instances, max_instances=max_instances)
        self._touch(region)
        return "creado (ensayo)"

    async def scale(self, region: str, min_instances: int, max_instances: int) -> str:
        self.calls.append(("escalar", region))
        n = self.nodes[region]
        n.min_instances, n.max_instances = min_instances, max_instances
        self._touch(region)
        return "escalado (ensayo)"

    async def set_fault(self, region: str, fault: str | None) -> str:
        self.calls.append(("falla" if fault else "reparar", region))
        if fault is not None and fault not in NODE_FAULTS:
            raise ValueError(f"falla desconocida: {fault}")
        self.nodes[region].fault = fault
        self._touch(region)
        return "revisión nueva (ensayo)"

    async def delete(self, region: str) -> str:
        self.calls.append(("borrar", region))
        self.nodes.pop(region, None)
        self.pending.pop(region, None)
        return "borrado (ensayo)"

    async def probe(self, state: NodeState) -> Probe:
        n = self.nodes.get(state.region)
        if n is None:
            return Probe(None, None, "no existe")
        if n.fault == "caida":
            return Probe(None, 503)
        base = 40 + self.rng.gauss(0, 4)
        return Probe(base + (600 if n.fault == "latencia" else 0), 200)

    # --- agentes del mercado real ----------------------------------------------------
    async def list_agents(self) -> dict[str, AgentState]:
        for agent_id, a in self.agents.items():
            left = self.agent_pending.get(agent_id, 0)
            a.reconciling, a.ready = left > 0, left == 0
            self.agent_pending[agent_id] = max(0, left - 1)
        return {k: replace(a) for k, a in self.agents.items()}

    async def ensure_agent(self, agent_id: str, region: str, warm: bool) -> str:
        self._check(region)
        self.calls.append(("agente", agent_id))
        a = self.agents.get(agent_id)
        if a is None:
            self.agents[agent_id] = AgentState(agent_id, region, uri=f"https://ensayo/{agent_id}", warm=warm,
                                               revision="r1")
        else:
            a.warm, a.revision = warm, f"r{int((a.revision or 'r0')[1:]) + 1}"
        self.agent_pending[agent_id] = self.settle
        self.cold[agent_id] = not warm
        return "agente listo (ensayo)"

    async def delete_agent(self, agent_id: str, region: str) -> str:
        self.calls.append(("borrar agente", agent_id))
        self.agents.pop(agent_id, None)
        return "borrado (ensayo)"

    async def work(self, state: AgentState, n: int) -> list[WorkResult]:
        a = self.agents.get(state.id)
        if a is None:
            return [WorkResult(None, None, None)] * n
        out = []
        for _ in range(n):
            server = 5 + abs(self.rng.gauss(0, 1))
            latency = 40 + server + self.rng.gauss(0, 4)
            if not a.warm and self.cold.get(state.id, True):
                latency += 1400  # arranque en frío: más de lo que tolera el plazo de 1 s
                self.cold[state.id] = False
            out.append(WorkResult(latency, server, 200))
        if not a.warm:
            self.cold[state.id] = self.rng.random() < 0.5  # sin tráfico, la instancia se apaga
        return out
