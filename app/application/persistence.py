"""Sobrevivir a que la API escale a cero: una foto del estado, guardada fuera del proceso.

Cloud Run apaga la instancia tras unos minutos sin peticiones, y la sala vive en
memoria. En lugar de un repositorio remoto (una escritura por cada orden), se
guarda una foto entera:

- después de un cambio, como mucho una vez cada `every` segundos;
- y al apagarse la instancia, que Cloud Run avisa con SIGTERM.

Al arrancar, si hay una foto válida, se restaura: el mismo código de sala, las
mismas cuentas y tokens, los mismos mercados. Si la foto no se puede leer, no es
de este código o es vieja, se empieza de cero. Nunca impide arrancar.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from .ports import Repository, StateCodec, StateStore

log = logging.getLogger("oraculo.estado")


class Part(Protocol):
    def snapshot(self) -> dict: ...

    def restore(self, state: dict) -> None: ...


class Persistence:
    def __init__(self, store: StateStore, codec: StateCodec, repo: Repository, parts: dict[str, Part],
                 every: float = 5.0, clock: Callable[[], float] = time.time):
        self.store = store
        self.codec = codec
        self.repo = repo
        self.parts = parts
        self.every = every
        self.clock = clock
        self.dirty = False
        self.last_save = 0.0

    def touch(self) -> None:
        """Algo cambió: la próxima oportunidad guarda."""
        self.dirty = True

    async def maybe_save(self) -> None:
        if self.dirty and self.clock() - self.last_save >= self.every:
            await self.save()

    async def save(self) -> bool:
        now = self.clock()
        # La foto se toma y se serializa sin ceder el control: ninguna ruta la ve a medias.
        with self.repo.transaction():
            blob = self.codec.dumps({name: p.snapshot() for name, p in self.parts.items()}, now)
        self.dirty, self.last_save = False, now
        try:
            await self.store.save(blob)
        except Exception as exc:  # noqa: BLE001 — sin foto se sigue atendiendo; se reintenta
            self.dirty = True
            log.warning("no se pudo guardar el estado (%s: %s)", type(exc).__name__, exc)
            return False
        return True

    async def restore(self) -> bool:
        try:
            blob = await self.store.load()
            if blob is None:
                return False
            state = self.codec.loads(blob, self.clock())
            with self.repo.transaction():
                for name, part in self.parts.items():
                    if state.get(name) is not None:
                        part.restore(state[name])
        except Exception as exc:  # noqa: BLE001 — una foto inservible no impide arrancar
            log.warning("se empieza de cero: la foto del estado no sirve (%s: %s)", type(exc).__name__, exc)
            return False
        log.info("estado restaurado desde la foto")
        return True
