"""Casos de uso de la nube simulada: correr, pausar, inyectar fallas y pedir topologías.

En producción el laboratorio está apagado: solo se usan las topologías.

La simulación avanza de forma perezosa: cada petición calcula cuántos ticks
tocan según el reloj y los ejecuta. No hay tareas en segundo plano, que Cloud
Run congelaría entre peticiones, y los tests controlan el tiempo con un reloj falso.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from ..domain.cloud.simulation import Simulation
from ..domain.errors import SimulationError
from ..domain.verdict import Verdict
from .ports import TopologyGenerator
from .views import simulation_view

MAX_CATCHUP = 50  # ticks por petición como máximo, para que una pausa larga no congele la API


class CloudService:
    def __init__(self, sim: Simulation, generator: TopologyGenerator, tick_seconds: float = 1.0,
                 clock: Callable[[], float] = time.time, lab: bool = True):
        self.sim = sim
        self.lab = lab  # sin laboratorio solo quedan las topologías, que decide la política
        self.generator = generator
        self.tick_seconds = tick_seconds
        self.clock = clock
        self.running = False
        self._last = clock()
        self._lock = threading.RLock()

    def _advance(self) -> None:
        now = self.clock()
        if not self.running:
            self._last = now
            return
        due = int((now - self._last) / self.tick_seconds)
        for _ in range(min(due, MAX_CATCHUP)):
            self.sim.tick()
        self._last = now if due > MAX_CATCHUP else self._last + due * self.tick_seconds

    def view(self) -> dict:
        with self._lock:
            self._advance()
            return simulation_view(self.sim, self.running, self.generator) | {"lab": self.lab}

    def _require_lab(self) -> None:
        if not self.lab:
            raise SimulationError("el laboratorio simulado está apagado: aquí todo es real")

    def start(self) -> dict:
        self._require_lab()
        with self._lock:
            self._advance()
            self.running = True
            self._last = self.clock()
            return self.view()

    def pause(self) -> dict:
        self._require_lab()
        with self._lock:
            self._advance()
            self.running = False
            return self.view()

    def step(self, n: int = 1) -> dict:
        if not 1 <= n <= MAX_CATCHUP:
            raise SimulationError(f"pasos fuera de [1, {MAX_CATCHUP}]")
        self._require_lab()
        with self._lock:
            self._advance()
            for _ in range(n):
                self.sim.tick()
            return self.view()

    def inject(self, kind: str, target: str | None = None) -> dict:
        self._require_lab()
        with self._lock:
            self._advance()
            self.sim.inject(kind, target)
            return self.view()

    async def propose(self, source: str) -> dict:
        if source == "evolutivo":
            with self._lock:
                self._advance()
                self.sim.propose_evolutionary()
                return self.view()
        if source != "generativo":
            raise SimulationError(f"fuente desconocida: {source}")
        with self._lock:
            self._advance()
            brief = self.sim.brief()
        # Fuera del lock: el modelo tarda y la simulación sigue corriendo.
        draft = await self.generator.propose(brief)
        with self._lock:
            self._advance()
            self.sim.review("generativo", draft.model, draft.raw, list(draft.trace), draft.reasoning)
            return self.view()

    def judge(self, predicate: str) -> Verdict:
        self._require_lab()
        with self._lock:
            self._advance()
            return self.sim.judge(predicate)
