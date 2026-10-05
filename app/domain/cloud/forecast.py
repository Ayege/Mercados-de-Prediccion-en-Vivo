"""Predicción de demanda: Holt-Winters aditivo (nivel, tendencia y estacionalidad).

Es el modelo más pequeño que capta un ciclo diario. Aprende en línea, una
observación por tick, sin ver nunca el futuro.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HoltWinters:
    period: int = 24
    alpha: float = 0.35
    beta: float = 0.05
    gamma: float = 0.3
    level: float | None = None
    trend: float = 0.0
    season: list[float] = field(default_factory=list)
    t: int = 0
    warm: list[float] = field(default_factory=list)  # primer ciclo, para inicializar

    def forecast(self, h: int = 1) -> float:
        """Antes de completar un ciclo, repite la última observación (pronóstico ingenuo)."""
        if self.level is None:
            return self.warm[-1] if self.warm else 0.0
        return max(0.0, self.level + h * self.trend + self.season[(self.t + h - 1) % self.period])

    def update(self, y: float) -> None:
        i = self.t % self.period
        self.t += 1
        if self.level is None:
            self.warm.append(y)
            if len(self.warm) == self.period:
                # Nivel = media del primer ciclo; estacionalidad = desvío de cada hora.
                self.level = sum(self.warm) / self.period
                self.season = [x - self.level for x in self.warm]
            return
        prev, s = self.level, self.season[i]
        self.level = self.alpha * (y - s) + (1 - self.alpha) * (self.level + self.trend)
        self.trend = self.beta * (self.level - prev) + (1 - self.beta) * self.trend
        self.season[i] = self.gamma * (y - self.level) + (1 - self.gamma) * s


@dataclass
class Holt:
    """Suavizado doble (nivel y tendencia), para series sin ciclo: el tráfico de la sala."""

    alpha: float = 0.4
    beta: float = 0.2
    level: float | None = None
    trend: float = 0.0

    def forecast(self, h: int = 1) -> float:
        return 0.0 if self.level is None else max(0.0, self.level + h * self.trend)

    def update(self, y: float) -> None:
        if self.level is None:
            self.level = y
            return
        prev = self.level
        self.level = self.alpha * y + (1 - self.alpha) * (self.level + self.trend)
        self.trend = self.beta * (self.level - prev) + (1 - self.beta) * self.trend
