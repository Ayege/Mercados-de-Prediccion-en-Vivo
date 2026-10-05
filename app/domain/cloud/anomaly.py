"""Detección de anomalías: media y varianza exponenciales, alarma por z-score.

El detector solo ve métricas. No sabe qué falla inyectó el ponente, así que
puede tardar, equivocarse o no ver nada, y la vista muestra cuándo pasa.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass
class Detector:
    z_threshold: float = 4.0
    min_jump: float = 0.0  # salto absoluto mínimo, para no alarmar por ruido en series planas
    alpha: float = 0.15
    warmup: int = 10
    mean: float = 0.0
    var: float = 0.0
    n: int = 0

    def observe(self, x: float) -> float | None:
        """Devuelve el z-score si `x` es anómalo; si no, lo incorpora a la línea base."""
        if self.n >= self.warmup:
            z = (x - self.mean) / sqrt(self.var + 1e-9)
            if z > self.z_threshold and x - self.mean > self.min_jump:
                return z  # lo anómalo no contamina la línea base
        if self.n == 0:
            self.mean = x
        else:
            d = x - self.mean
            self.mean += self.alpha * d
            self.var = (1 - self.alpha) * (self.var + self.alpha * d * d)
        self.n += 1
        return None
