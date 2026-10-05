"""Nube de ensayo en memoria: se comporta como Cloud Run sin costar nada.

Los cambios tardan un par de ciclos en aplicarse (como `reconciling`), la
latencia tiene ruido y las fallas se ven en el sondeo igual que en la real.
"""
from __future__ import annotations

import random
from dataclasses import replace

from ...domain.cloud.catalog import REGIONS
from ...domain.cloud.infra import NODE_FAULTS, NodeState, Probe


class FakeNodeGateway:
    name = "ensayo"

    def __init__(self, seed: int = 11, settle: int = 2):
        self.rng = random.Random(seed)  # noqa: S311 — ruido de una nube de ensayo
        self.settle = settle
        self.nodes: dict[str, NodeState] = {}
        self.pending: dict[str, int] = {}
        self.calls: list[tuple[str, str]] = []

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
