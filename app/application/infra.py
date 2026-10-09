"""Controlador de infraestructura real: el bucle que convierte decisiones en acciones.

Cada ciclo:
1. Observa los servicios `oraculo-nodo-*` que existen de verdad.
2. Mide la demanda real (peticiones de la sala a la API) y la predice con Holt.
3. Sondea los nodos encendidos y pasa la latencia por el detector de anomalías.
4. Calcula el estado deseado: la topología adoptada por la simulación, con tantas
   instancias mínimas como pida la predicción.
5. `ActuationPolicy` recorta el deseo, planifica y revisa cada acción.
6. Solo entonces, si la actuación está activa, llama a la nube.

El modelo generativo nunca llega aquí directamente: su propuesta pasó antes por
`TopologyPolicy` y la simulación tuvo que adoptarla.

Costo: no hay bucle en segundo plano. El ciclo corre dentro de las consultas de
la proyección cuando toca (`maybe_cycle`), así la API puede usar facturación por
petición y escalar a cero. Como los nodos sí cobran aunque la API duerma, la
vigilia (`vigil`) los borra si nadie mira la proyección durante `ttl` segundos.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from math import ceil

from ..domain.cloud.anomaly import Detector
from ..domain.cloud.forecast import Holt
from ..domain.cloud.infra import NODE_FAULTS, Action, ActuationPolicy, NodeState, distribute, plan
from ..domain.cloud.predicates import REAL
from ..domain.errors import SimulationError
from ..domain.verdict import Verdict
from .ports import NodeGateway
from .real_market import RealMarket

log = logging.getLogger("oraculo.infra")


@dataclass
class RealFault:
    id: int
    region: str
    kind: str
    at: float
    repaired: float | None = None


@dataclass
class RealIncident:
    id: int
    region: str
    at: float
    latency_ms: float | None
    z: float
    repair_sent: float | None = None
    repaired: float | None = None
    fault: int | None = None


@dataclass
class LogEntry:
    at: float
    action: Action
    allowed: bool
    why: str
    result: str = ""


@dataclass
class Probed:
    at: float
    latency_ms: float | None
    status: int | None
    error: str = ""


@dataclass
class InfraState:
    actual: dict[str, NodeState] = field(default_factory=dict)
    probes: dict[str, list[Probed]] = field(default_factory=dict)
    rps: list[tuple[float, float, float]] = field(default_factory=list)  # (t, real, predicho)
    notes: list[str] = field(default_factory=list)
    log: list[LogEntry] = field(default_factory=list)
    faults: list[RealFault] = field(default_factory=list)
    incidents: list[RealIncident] = field(default_factory=list)
    last_cycle: float | None = None
    last_error: str = ""


class InfraController:
    UNREACHABLE_MS = 3000.0

    def __init__(self, gateway: NodeGateway, topology: Callable[[], dict[str, int]], mode: str,
                 policy: ActuationPolicy | None = None, rps_per_instance: float = 10.0,
                 interval: float = 10.0, clock: Callable[[], float] = time.time, ttl: float = 1800.0,
                 market: RealMarket | None = None):
        self.gateway = gateway
        self.topology = topology
        self.mode = mode
        self.policy = policy or ActuationPolicy()
        self.rps_per_instance = rps_per_instance
        self.interval = interval
        self.clock = clock
        self.ttl = ttl
        self.market = market  # agentes reales que venden peticiones reales; comparte frenos con los nodos
        # Un proceso recién arrancado asume que nadie mira: si Cloud Scheduler lo despierta
        # para la vigilia, borra los nodos que quedaron de una sesión anterior.
        self.last_seen = clock() - ttl
        self.active = False  # la actuación arranca en pausa: el ponente la enciende
        self.state = InfraState()
        self.forecaster = Holt()
        self.detectors: dict[str, Detector] = {}
        self.streak: dict[str, int] = {}
        self.last_change: dict[str, float] = {}
        self._requests = 0
        self._since = clock()
        self._lock = asyncio.Lock()

    # --- señales ---------------------------------------------------------------
    def count_request(self) -> None:
        """Lo llama el middleware HTTP: cada petición de la sala es demanda real."""
        self._requests += 1

    def _measure_demand(self, now: float) -> float:
        elapsed = max(1e-6, now - self._since)
        rps = self._requests / elapsed
        self._requests, self._since = 0, now
        predicted = self.forecaster.forecast()
        self.forecaster.update(rps)
        self.state.rps.append((now, round(rps, 2), round(predicted, 2)))
        self.state.rps = self.state.rps[-90:]
        return self.forecaster.forecast()

    # --- el ciclo --------------------------------------------------------------
    async def cycle(self) -> None:
        async with self._lock:
            now = self.clock()
            try:
                self.state.actual = await self.gateway.list()
            except Exception as exc:
                self.state.last_error = f"no se pudo listar los nodos ({type(exc).__name__}: {exc})"
                log.warning(self.state.last_error)
                return
            self.state.last_error = ""
            self.state.notes = []
            forecast = self._measure_demand(now)
            repairs = await self._probe_and_detect(now)

            total_min = ceil(forecast / self.rps_per_instance) if forecast > 0.05 else 0
            desired, notes = self.policy.clamp(distribute(self.topology(), total_min))
            self.state.notes.insert(0, f"demanda prevista {forecast:.1f} req/s → "
                                       f"{total_min} instancia(s) mínima(s)")
            self.state.notes += notes
            why = f"topología adoptada y demanda prevista de {forecast:.1f} req/s"
            await self._execute(plan(desired, self.state.actual, why) + repairs, now)
            if self.market:
                # La demanda real de este ciclo: la predicción en req/s por la duración del ciclo.
                await self.market.cycle(int(round(forecast * self.interval)), self.active)
            self.state.last_cycle = now

    async def _probe_and_detect(self, now: float) -> list[Action]:
        repairs = []
        for region, st in self.state.actual.items():
            if not (st.exists and st.ready and st.uri and st.min_instances >= 1 and not st.reconciling):
                continue  # sin instancias encendidas, sondear solo mediría arranques en frío
            p = await self.gateway.probe(st)
            history = self.state.probes.setdefault(region, [])
            history.append(Probed(now, p.latency_ms, p.status, p.error))
            del history[:-30]
            if p.status in (401, 403):
                self.state.notes.append(f"{region}: sin permiso para sondear ({p.status}); no se evalúa")
                continue
            latency = p.latency_ms if p.latency_ms is not None else self.UNREACHABLE_MS
            z = self.detectors.setdefault(region, Detector(min_jump=250, warmup=5)).observe(latency)
            self.streak[region] = self.streak.get(region, 0) + 1 if z is not None else 0
            open_incident = next((i for i in self.state.incidents
                                  if i.region == region and i.repaired is None), None)
            if open_incident:
                if z is None and not st.fault:
                    # El nodo volvió a responder normal después de la reparación.
                    open_incident.repaired = now
                    for f in self.state.faults:
                        if f.region == region and f.repaired is None:
                            f.repaired = now
                elif open_incident.repair_sent is None:
                    repairs.append(Action("reparar", region, reason="reintento: el incidente sigue abierto"))
            elif z is not None and self.streak[region] >= 2:
                fault = next((f.id for f in self.state.faults
                              if f.region == region and f.repaired is None), None)
                self.state.incidents.append(RealIncident(len(self.state.incidents) + 1, region, now,
                                                         p.latency_ms, round(z, 1), fault=fault))
                repairs.append(Action("reparar", region,
                                      reason=f"latencia anómala (z {z:.1f}) dos veces seguidas"))
        return repairs

    async def _execute(self, actions: list[Action], now: float) -> None:
        for r in self.policy.check(actions, self.state.actual, self.last_change, now):
            entry = LogEntry(now, r.action, r.allowed, r.why)
            if r.allowed and not self.active:
                entry.allowed, entry.why = False, "actuación en pausa: el ponente debe activarla"
            elif r.allowed:
                entry.result = await self._apply(r.action, now)
            self.state.log.append(entry)
        self.state.log = self.state.log[-40:]

    async def _apply(self, a: Action, now: float) -> str:
        try:
            if a.kind == "crear":
                result = await self.gateway.create(a.region, a.min_instances or 0, a.max_instances or 1)
            elif a.kind == "escalar":
                result = await self.gateway.scale(a.region, a.min_instances or 0, a.max_instances or 1)
            elif a.kind == "borrar":
                result = await self.gateway.delete(a.region)
            elif a.kind == "falla":
                result = await self.gateway.set_fault(a.region, a.fault)
            else:  # reparar: una revisión nueva, sana
                result = await self.gateway.set_fault(a.region, None)
                for i in self.state.incidents:
                    if i.region == a.region and i.repair_sent is None:
                        i.repair_sent = now
        except Exception as exc:
            log.warning("acción %s en %s falló: %s", a.kind, a.region, exc)
            return f"error: {type(exc).__name__}: {exc}"[:300]
        self.last_change[a.region] = now
        return result

    # --- acciones del ponente --------------------------------------------------
    def set_active(self, active: bool) -> None:
        self.active = active

    async def inject(self, region: str, kind: str) -> None:
        if kind not in NODE_FAULTS:
            raise SimulationError(f"falla desconocida: {kind}")
        async with self._lock:
            now = self.clock()
            st = self.state.actual.get(region)
            if st is None or not st.exists:
                raise SimulationError(f"no hay un nodo real en {region}")
            if not self.active:
                raise SimulationError("la actuación está en pausa")
            warm = self.detectors.get(region)
            if warm is None or warm.n < warm.warmup:
                raise SimulationError(f"el detector de {region} aún no tiene línea base: espera unos sondeos "
                                      "(el nodo necesita al menos una instancia mínima encendida)")
            await self._execute([Action("falla", region, fault=kind, reason="inyectada por el ponente")], now)
            last = self.state.log[-1] if self.state.log else None
            if last and last.allowed and not last.result.startswith("error"):
                self.state.faults.append(RealFault(len(self.state.faults) + 1, region, kind, now))

    async def shutdown(self) -> None:
        """Interruptor de emergencia: pausa la actuación y borra todos los nodos y agentes."""
        async with self._lock:
            self.active = False
            now = self.clock()
            if self.market:
                for line in await self.market.shutdown():
                    self.state.notes.append(f"agente {line}")
            for region, st in self.state.actual.items():
                if st.exists:
                    entry = LogEntry(now, Action("borrar", region, reason="apagado de emergencia"), True,
                                     "el apagado siempre está permitido")
                    entry.result = await self._apply(entry.action, now)
                    self.state.log.append(entry)

    # --- foto del estado ---------------------------------------------------------
    PERSISTED = ("state", "forecaster", "detectors", "streak", "last_change")

    def snapshot(self) -> dict:
        """Fallas, incidentes y lo aprendido. Ni `active` ni `last_seen`: al despertar, la
        actuación vuelve a pausa y la vigilia puede borrar lo que quedó encendido."""
        state = {k: getattr(self, k) for k in self.PERSISTED}
        return state | {"market": self.market.snapshot() if self.market else None}

    def restore(self, state: dict) -> None:
        for k in self.PERSISTED:
            setattr(self, k, state[k])
        if self.market and state["market"]:
            self.market.restore(state["market"])

    # --- costo ------------------------------------------------------------------
    def touch(self) -> None:
        """Alguien está mirando la proyección: la vigilia no apaga nada."""
        self.last_seen = self.clock()

    async def maybe_cycle(self) -> None:
        """Corre un ciclo si toca y si no hay otro en curso. Nunca hace esperar dos veces."""
        if self._lock.locked():
            return
        last = self.state.last_cycle
        if last is not None and self.clock() - last < self.interval:
            return
        await self.cycle()

    async def vigil(self) -> dict:
        """Lo llama Cloud Scheduler. Si nadie mira hace más de `ttl`, borra todos los nodos."""
        idle = self.clock() - self.last_seen
        if idle < self.ttl:
            return {"apagado": False, "inactivo_s": round(idle), "ttl_s": self.ttl}
        try:
            self.state.actual = await self.gateway.list()
        except Exception as exc:
            return {"apagado": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
        had = [r for r, n in self.state.actual.items() if n.exists]
        if self.market and await self.market.exists():
            had.append("agentes del mercado real")
        if had:
            await self.shutdown()
        return {"apagado": bool(had), "nodos": had, "inactivo_s": round(idle), "ttl_s": self.ttl}

    # --- juez ------------------------------------------------------------------
    def judge(self, predicate: str) -> Verdict:
        if predicate not in REAL:
            raise SimulationError(f"predicado desconocido: {predicate}")
        if predicate == "cooperacion_real":
            if self.market is None:
                why = "el mercado real no está conectado"
                return Verdict("UNRESOLVED", 0.0, why, model="mercado real", trace=[f"{why} → UNRESOLVED"])
            return self.market.judge_cooperation()
        trace = [f"infraestructura {self.mode} ({self.gateway.name})"]
        first = self.state.faults[0] if self.state.faults else None
        if first is None or first.repaired is None:
            why = ("todavía no hubo una falla real" if first is None
                   else f"la falla en {first.region} sigue abierta")
            trace.append(f"{why} → UNRESOLVED")
            return Verdict("UNRESOLVED", 0.0, why, model="infraestructura", trace=trace)
        took = first.repaired - first.at
        outcome = "YES" if took < 120 else "NO"
        why = f"la falla en {first.region} se reparó en {took:.0f} s"
        trace.append(f"{why} → {outcome}")
        return Verdict(outcome, 1.0, why, model="infraestructura", trace=trace)

    # --- vista -----------------------------------------------------------------
    def view(self, detailed: bool = True) -> dict:
        """`detailed=False` es la vista pública: sin mensajes de error de la API de Google,
        que revelan el proyecto, las cuentas y los permisos."""
        st = self.state
        faults = {f.id: f for f in st.faults}

        def safe(text: str) -> str:
            if detailed or not text:
                return text
            return "error (los detalles solo los ve el ponente)" if "error" in text.lower() else text

        return {
            "mode": self.mode,
            "gateway": self.gateway.name,
            "active": self.active,
            "interval": self.interval,
            "ttl": self.ttl,
            "idle": round(self.clock() - self.last_seen),
            "last_cycle": st.last_cycle,
            "last_error": safe(st.last_error),
            "policy": {
                "regions": list(self.policy.regions), "max_services": self.policy.max_services,
                "max_min_per_region": self.policy.max_min_per_region,
                "max_max_per_region": self.policy.max_max_per_region,
                "max_total_min": self.policy.max_total_min,
                "seconds_between_changes": self.policy.seconds_between_changes,
            },
            "notes": [safe(n) for n in st.notes],
            "nodes": [
                {"region": n.region, "ready": n.ready, "reconciling": n.reconciling, "uri": n.uri,
                 "min": n.min_instances, "max": n.max_instances, "fault": n.fault, "revision": n.revision,
                 "latency": [p.latency_ms for p in st.probes.get(n.region, [])],
                 "last_status": (st.probes.get(n.region) or [Probed(0, None, None)])[-1].status}
                for n in sorted(st.actual.values(), key=lambda n: n.region) if n.exists
            ],
            "rps": [{"t": t, "real": r, "predicho": p} for t, r, p in st.rps],
            "log": [
                {"at": e.at, "kind": e.action.kind, "region": e.action.region, "min": e.action.min_instances,
                 "max": e.action.max_instances, "fault": e.action.fault, "reason": e.action.reason,
                 "allowed": e.allowed, "why": e.why, "result": safe(e.result)}
                for e in st.log[-15:]
            ][::-1],
            "faults": [{"id": f.id, "region": f.region, "kind": f.kind, "at": f.at, "repaired": f.repaired}
                       for f in st.faults][::-1],
            "incidents": [
                {"id": i.id, "region": i.region, "at": i.at, "latency_ms": i.latency_ms, "z": i.z,
                 "repair_sent": i.repair_sent, "repaired": i.repaired, "fault": i.fault,
                 "detected_after": round(i.at - faults[i.fault].at, 1) if i.fault else None,
                 "repaired_after": (round(i.repaired - faults[i.fault].at, 1)
                                    if i.fault and i.repaired else None)}
                for i in st.incidents
            ][::-1],
            "fault_kinds": NODE_FAULTS,
            "market": self.market.view(detailed) if self.market else None,
        }
