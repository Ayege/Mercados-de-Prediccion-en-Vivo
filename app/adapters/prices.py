"""Precios de Cloud Run: del catálogo público de Cloud Billing, o fijos para ensayar.

Se usan los precios de lista con facturación por petición. El nivel gratuito
mensual no se descuenta: el costo que muestra la demo nunca es menor que el real.
"""
from __future__ import annotations

import time

import httpx

from ..domain.cloud.catalog import REGIONS
from ..domain.cloud.real_market import PriceTable, RegionPrice
from .google_auth import AccessToken

CLOUD_RUN = "services/152E-C115-5142"
BASE = "https://cloudbilling.googleapis.com/v1"

# Foto del catálogo tomada el 2026-10-05, para el modo ensayo y los tests.
# Nivel 1: us-east1, us-central1, europe-west1. Nivel 2: el resto de estas regiones.
_T1 = RegionPrice(cpu_s=2.4e-05, mem_s=2.5e-06, idle_cpu_s=2.5e-06, idle_mem_s=2.5e-06)
_T2 = RegionPrice(cpu_s=3.36e-05, mem_s=3.5e-06, idle_cpu_s=3.5e-06, idle_mem_s=3.5e-06)
SNAPSHOT = PriceTable(
    regions={r: (_T1 if r in ("us-east1", "us-central1", "europe-west1") else _T2) for r in REGIONS},
    per_request=4e-07,
    source="foto del catálogo (2026-10-05)",
)

# Descripción del SKU → campo de RegionPrice. Nivel 2 tiene la misma descripción con "Tier 2".
SKUS = {
    "Services CPU (Request-based billing)": "cpu_s",
    "Services Memory (Request-based billing)": "mem_s",
    "Services Min Instance CPU (Request-based billing)": "idle_cpu_s",
    "Services Min Instance Memory (Request-based billing)": "idle_mem_s",
}


def _price(sku: dict) -> float:
    """Precio del último tramo (el que aplica pasado el nivel gratuito)."""
    tier = sku["pricingInfo"][0]["pricingExpression"]["tieredRates"][-1]["unitPrice"]
    return int(tier.get("units", "0")) + tier.get("nanos", 0) / 1e9


def parse(skus: list[dict], fetched_at: float = 0.0) -> PriceTable:
    fields: dict[str, dict[str, float]] = {r: {} for r in REGIONS}
    per_request = None
    for sku in skus:
        desc = sku.get("description", "").replace("Tier 2 ", "").replace("  ", " ")
        if desc == "Requests":
            per_request = _price(sku)
        field = SKUS.get(desc)
        if field is None:
            continue
        for region in sku.get("serviceRegions", []):
            if region in fields:
                fields[region][field] = _price(sku)
    missing = [r for r, f in fields.items() if len(f) < len(SKUS)]
    if missing or per_request is None:
        raise ValueError(f"el catálogo no trae todos los precios (faltan {missing or 'peticiones'})")
    regions = {r: RegionPrice(**f) for r, f in fields.items()}
    return PriceTable(regions, per_request, "Cloud Billing Catalog API", fetched_at)


class CloudBillingPrices:
    """Lee el catálogo público de Cloud Billing. Cachea una hora: los precios no cambian a cada rato."""

    def __init__(self, project: str, ttl: float = 3600.0):
        self.project = project
        self.ttl = ttl
        self._token = AccessToken()
        self._cache: PriceTable | None = None

    async def get(self) -> PriceTable:
        if self._cache and time.time() - self._cache.fetched_at < self.ttl:
            return self._cache
        token = await self._token.get()
        # Sin x-goog-user-project: exigiría serviceusage.services.use, un permiso más. Con una cuenta
        # de servicio, la cuota se atribuye a su propio proyecto.
        headers = {"Authorization": f"Bearer {token}"}
        skus, page = [], ""
        async with httpx.AsyncClient(timeout=20) as client:
            while True:
                r = await client.get(f"{BASE}/{CLOUD_RUN}/skus", headers=headers,
                                     params={"currencyCode": "USD", "pageSize": 5000, "pageToken": page})
                if r.status_code >= 400:
                    error = r.json().get("error", {}) if r.content else {}
                    message = error.get("message", r.reason_phrase)
                    raise RuntimeError(f"catálogo de Cloud Billing: {r.status_code}: {message}"[:300])
                body = r.json()
                skus += body.get("skus", [])
                page = body.get("nextPageToken", "")
                if not page:
                    break
        self._cache = parse(skus, time.time())
        return self._cache


class FixedPrices:
    """La foto del catálogo: para ensayar sin red con números reales de un día concreto."""

    async def get(self) -> PriceTable:
        return SNAPSHOT
