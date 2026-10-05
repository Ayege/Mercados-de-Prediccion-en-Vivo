"""Infraestructura real: del estado deseado a acciones, y la política que las limita.

Es la segunda compuerta. `TopologyPolicy` decide si un diseño es bueno;
`ActuationPolicy` decide si se puede *ejecutar* sobre una cuenta real de Google
Cloud: regiones permitidas, topes de instancias, límite de cambios por minuto y
solo servicios propios. La política recorta el deseo antes de planificar y
vuelve a revisar cada acción antes de ejecutarla.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor

from .catalog import REGIONS

NODE_PREFIX = "oraculo-nodo-"
NODE_FAULTS = {"latencia": "el nodo tarda 600 ms en responder", "caida": "el nodo responde 503"}
MUTATING = ("crear", "escalar", "falla", "reparar")


def service_name(region: str) -> str:
    return NODE_PREFIX + region


@dataclass(frozen=True)
class NodeSpec:
    min_instances: int
    max_instances: int


@dataclass
class NodeState:
    region: str
    exists: bool = True
    ready: bool = False
    reconciling: bool = False
    uri: str | None = None
    min_instances: int = 0
    max_instances: int = 0
    fault: str | None = None
    revision: str | None = None


@dataclass(frozen=True)
class Probe:
    latency_ms: float | None  # None: no respondió o respondió con error
    status: int | None = None
    error: str = ""


@dataclass(frozen=True)
class Action:
    kind: str  # crear | escalar | borrar | falla | reparar
    region: str
    min_instances: int | None = None
    max_instances: int | None = None
    fault: str | None = None
    reason: str = ""


def distribute(topology: dict[str, int], total_min: int) -> dict[str, NodeSpec]:
    """Reparte `total_min` instancias mínimas entre regiones según sus réplicas (mayor resto).

    Las réplicas de la topología son el máximo de cada región.
    """
    used = {r: n for r, n in topology.items() if n > 0}
    if not used:
        return {}
    weight = sum(used.values())
    total_min = min(total_min, weight)
    exact = {r: total_min * n / weight for r, n in used.items()}
    mins = {r: floor(x) for r, x in exact.items()}
    leftover = total_min - sum(mins.values())
    for r in sorted(used, key=lambda r: (exact[r] - mins[r], r), reverse=True)[:leftover]:
        mins[r] += 1
    return {r: NodeSpec(mins[r], used[r]) for r in used}


def plan(desired: dict[str, NodeSpec], actual: dict[str, NodeState], why: str) -> list[Action]:
    actions = []
    for region, spec in sorted(desired.items()):
        st = actual.get(region)
        if st is None or not st.exists:
            actions.append(Action("crear", region, spec.min_instances, spec.max_instances, reason=why))
        elif (st.min_instances, st.max_instances) != (spec.min_instances, spec.max_instances):
            actions.append(Action("escalar", region, spec.min_instances, spec.max_instances, reason=why))
    for region, st in sorted(actual.items()):
        if st.exists and region not in desired:
            actions.append(Action("borrar", region, reason="la topología ya no incluye esta región"))
    return actions


@dataclass(frozen=True)
class Ruling:
    action: Action
    allowed: bool
    why: str


@dataclass(frozen=True)
class ActuationPolicy:
    regions: tuple[str, ...] = tuple(REGIONS)
    max_services: int = 3
    max_min_per_region: int = 1
    max_max_per_region: int = 2
    max_total_min: int = 2  # las instancias mínimas cobran aunque nadie las use
    max_calls_per_cycle: int = 3
    seconds_between_changes: float = 60.0

    def clamp(self, desired: dict[str, NodeSpec]) -> tuple[dict[str, NodeSpec], list[str]]:
        """Recorta el estado deseado a lo que esta cuenta permite, y dice qué recortó."""
        notes, out = [], {}
        for region, spec in sorted(desired.items()):
            if region not in self.regions:
                notes.append(f"{region}: región no permitida, se omite")
                continue
            if len(out) == self.max_services:
                notes.append(f"{region}: más de {self.max_services} servicios, se omite")
                continue
            mx = min(spec.max_instances, self.max_max_per_region)
            mn = min(spec.min_instances, self.max_min_per_region, mx)
            if (mn, mx) != (spec.min_instances, spec.max_instances):
                notes.append(f"{region}: {spec.min_instances}–{spec.max_instances} recortado a {mn}–{mx}")
            out[region] = NodeSpec(mn, mx)
        excess = sum(s.min_instances for s in out.values()) - self.max_total_min
        for region in sorted(out, reverse=True):
            if excess <= 0:
                break
            if out[region].min_instances:
                out[region] = NodeSpec(out[region].min_instances - 1, out[region].max_instances)
                excess -= 1
                notes.append(f"{region}: mínimo total > {self.max_total_min}, baja una instancia")
        return out, notes

    def check(self, actions: list[Action], actual: dict[str, NodeState], last_change: dict[str, float],
              now: float) -> list[Ruling]:
        """Segunda revisión, acción por acción. Lo que no pasa queda registrado con su razón."""
        out: list[Ruling] = []
        calls = 0
        total_min = sum(s.min_instances for s in actual.values() if s.exists)
        services = sum(1 for s in actual.values() if s.exists)
        for a in actions:
            st = actual.get(a.region)
            why = ""
            if a.region not in self.regions:
                why = "región no permitida"
            elif calls >= self.max_calls_per_cycle:
                why = f"más de {self.max_calls_per_cycle} cambios en este ciclo, queda para el siguiente"
            elif a.kind != "crear" and (st is None or not st.exists):
                why = "el servicio no existe"
            elif st is not None and st.reconciling:
                why = "Cloud Run todavía está aplicando el cambio anterior"
            elif a.kind == "crear" and services >= self.max_services:
                why = f"ya hay {services} servicios (máximo {self.max_services})"
            elif a.kind in ("crear", "escalar"):
                mn, mx = a.min_instances or 0, a.max_instances or 0
                new_total = total_min - (st.min_instances if st and st.exists else 0) + mn
                if mn > self.max_min_per_region or mx > self.max_max_per_region or mn > mx:
                    why = f"instancias {mn}–{mx} fuera de los límites"
                elif new_total > self.max_total_min:
                    why = f"el mínimo total sería {new_total} (máximo {self.max_total_min})"
                elif (a.kind == "escalar"
                      and now - last_change.get(a.region, -1e9) < self.seconds_between_changes):
                    why = f"cambió hace menos de {self.seconds_between_changes:.0f} s"
                else:
                    total_min = new_total
            elif a.kind == "falla" and a.fault not in NODE_FAULTS:
                why = f"falla desconocida: {a.fault}"
            if why:
                out.append(Ruling(a, False, why))
                continue
            calls += 1
            if a.kind == "crear":
                services += 1
            out.append(Ruling(a, True, "permitida"))
        return out
