"""Nodos reales en Cloud Run, vía la Admin API v2.

Cada nodo es un servicio `oraculo-nodo-<región>` con la misma imagen que la API
y `APP_MODULE=app.node:app`. Las fallas se inyectan como una revisión nueva con
`NODO_FALLA`, y se reparan con otra revisión sin ella.

Defensa en profundidad, además de `ActuationPolicy`:
- Solo construye nombres con el prefijo `oraculo-nodo-` y regiones del catálogo.
- Solo lee o modifica servicios con la etiqueta `oraculo-demo=true`; si existe un
  servicio con ese nombre que no es suyo, lo ignora y nunca lo toca.
- Con `validate_only` (modo plan), Cloud Run valida cada escritura sin aplicarla.
"""
from __future__ import annotations

import time

import httpx

from ...domain.cloud.catalog import REGIONS
from ...domain.cloud.infra import NODE_FAULTS, NODE_PREFIX, NodeState, Probe, service_name
from ..google_auth import AccessToken, id_token

BASE = "https://run.googleapis.com/v2"
LABELS = {"oraculo-demo": "true", "oraculo-rol": "nodo"}
HEALTHY = "ninguna"


class CloudRunNodeGateway:
    def __init__(self, project: str, image: str, service_account: str, validate_only: bool = False,
                 timeout: float = 20.0):
        self.project = project
        self.image = image
        self.service_account = service_account
        self.validate_only = validate_only
        self.timeout = timeout
        self.name = "cloud-run (plan: validateOnly)" if validate_only else "cloud-run"
        self._token = AccessToken()

    # --- utilidades ------------------------------------------------------------
    def _parent(self, region: str) -> str:
        if region not in REGIONS:
            raise ValueError(f"región no permitida: {region}")
        return f"{BASE}/projects/{self.project}/locations/{region}/services"

    def _url(self, region: str) -> str:
        name = service_name(region)
        if not name.startswith(NODE_PREFIX):  # no un assert: python -O los elimina
            raise ValueError(f"nombre fuera del prefijo permitido: {name}")
        return f"{self._parent(region)}/{name}"

    @staticmethod
    def _ok(r: httpx.Response) -> None:
        """Como raise_for_status, pero con el mensaje de la API: el 403 dice qué permiso falta."""
        if r.status_code < 400:
            return
        try:
            message = r.json().get("error", {}).get("message", "")
        except ValueError:
            message = r.text
        raise RuntimeError(f"{r.status_code}: {message}"[:400])

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        token = await self._token.get()
        params = kw.pop("params", {})
        if self.validate_only and method != "GET":
            params["validateOnly"] = "true"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.request(method, url, params=params,
                                        headers={"Authorization": f"Bearer {token}"}, **kw)

    def _template(self, region: str, mn: int, mx: int, fault: str | None) -> dict:
        return {
            "serviceAccount": self.service_account,
            "scaling": {"minInstanceCount": mn, "maxInstanceCount": mx},
            # Un cuarto de vCPU basta para responder sondeos. Cloud Run exige concurrencia 1
            # con menos de una vCPU (comprobado con validateOnly).
            "maxInstanceRequestConcurrency": 1,
            "timeout": "10s",
            "labels": LABELS,
            "containers": [{
                "image": self.image,
                "env": [
                    {"name": "APP_MODULE", "value": "app.node:app"},
                    {"name": "NODO_REGION", "value": region},
                    {"name": "NODO_FALLA", "value": fault or HEALTHY},
                ],
                "resources": {"limits": {"cpu": "0.25", "memory": "256Mi"}, "cpuIdle": True},
            }],
        }

    @staticmethod
    def _state(region: str, svc: dict) -> NodeState:
        tmpl = svc.get("template", {})
        scaling = tmpl.get("scaling", {})
        containers = tmpl.get("containers") or [{}]
        env = {e["name"]: e.get("value", "") for e in containers[0].get("env", [])}
        fault = env.get("NODO_FALLA")
        return NodeState(
            region=region,
            ready=(svc.get("terminalCondition") or {}).get("state") == "CONDITION_SUCCEEDED",
            reconciling=bool(svc.get("reconciling")),
            uri=svc.get("uri"),
            min_instances=int(scaling.get("minInstanceCount", 0)),
            max_instances=int(scaling.get("maxInstanceCount", 0)),
            fault=fault if fault in NODE_FAULTS else None,
            revision=str(svc.get("latestReadyRevision", "")).rsplit("/", 1)[-1] or None,
        )

    async def _get_own(self, region: str) -> dict | None:
        r = await self._request("GET", self._url(region))
        if r.status_code == 404:
            return None
        self._ok(r)
        svc = r.json()
        if (svc.get("labels") or {}).get("oraculo-demo") != "true":
            return None  # existe con nuestro nombre pero no lo creamos nosotros: no se toca
        return svc

    async def _patch(self, region: str, change) -> str:
        svc = await self._get_own(region)
        if svc is None:
            raise RuntimeError(f"{service_name(region)} no existe o no es de esta demo")
        st = self._state(region, svc)
        mn, mx, fault = change(st)
        body = {"labels": LABELS, "template": self._template(region, mn, mx, fault), "etag": svc.get("etag")}
        r = await self._request("PATCH", self._url(region), json=body)
        self._ok(r)
        return "validado por Cloud Run" if self.validate_only else "revisión nueva solicitada"

    # --- puerto ----------------------------------------------------------------
    async def list(self) -> dict[str, NodeState]:
        out = {}
        for region in REGIONS:
            svc = await self._get_own(region)
            if svc is not None:
                out[region] = self._state(region, svc)
        return out

    async def create(self, region: str, min_instances: int, max_instances: int) -> str:
        body = {"labels": LABELS, "ingress": "INGRESS_TRAFFIC_ALL",
                "template": self._template(region, min_instances, max_instances, None)}
        r = await self._request("POST", self._parent(region),
                                params={"serviceId": service_name(region)}, json=body)
        self._ok(r)
        return "validado por Cloud Run" if self.validate_only else "creación solicitada"

    async def scale(self, region: str, min_instances: int, max_instances: int) -> str:
        return await self._patch(region, lambda st: (min_instances, max_instances, st.fault))

    async def set_fault(self, region: str, fault: str | None) -> str:
        if fault is not None and fault not in NODE_FAULTS:
            raise ValueError(f"falla desconocida: {fault}")
        return await self._patch(region, lambda st: (st.min_instances, st.max_instances, fault))

    async def delete(self, region: str) -> str:
        if await self._get_own(region) is None:
            return "no existía"
        r = await self._request("DELETE", self._url(region))
        self._ok(r)
        return "validado por Cloud Run" if self.validate_only else "borrado solicitado"

    async def probe(self, state: NodeState) -> Probe:
        if not state.uri:
            return Probe(None, None, "sin URL")
        try:
            token = await id_token(state.uri)
        except Exception as exc:
            return Probe(None, 401, f"sin token de identidad ({type(exc).__name__})")
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{state.uri}/salud", headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            return Probe(None, None, type(exc).__name__)
        ms = (time.perf_counter() - start) * 1000
        return Probe(ms if r.status_code == 200 else None, r.status_code)
