"""Verifica titulares: descarga la página del medio y lee el título que publicó.

El modelo puede proponer enlaces, pero el titular que se muestra nunca sale de
su texto: sale de la página. Si la página no carga, no es de un medio de la
lista, o redirige fuera de ella, el artículo no existe.

Solo se descargan dominios de la lista de medios (más el redirector del
grounding de Vertex AI, que solo se usa como salto), siempre por https, con
límite de tiempo y de tamaño.
"""
from __future__ import annotations

import asyncio
import html
import re
from urllib.parse import urljoin

import httpx

from ...domain.errors import MarketError
from ...domain.media import Article, MediaList, host_of

REDIRECTORS = {"vertexaisearch.cloud.google.com"}  # los enlaces del grounding pasan por aquí
MAX_BYTES = 600_000
MAX_HOPS = 4
HEADERS = {"User-Agent": "oraculo-demo/1.0 (verificador de titulares)", "Accept": "text/html"}
OG_TITLE = [
    re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', re.I),
]
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def headline_from(page: str) -> str:
    """El título que publicó el medio: og:title si existe, si no <title>."""
    for pattern in [*OG_TITLE, TITLE]:
        m = pattern.search(page)
        if m:
            return " ".join(html.unescape(m.group(1)).split())[:300]
    return ""


async def _download(client: httpx.AsyncClient, url: str) -> tuple[int, str, str]:
    async with client.stream("GET", url, headers=HEADERS, follow_redirects=False) as r:
        if r.is_redirect:
            return r.status_code, urljoin(url, r.headers.get("location", "")), ""
        body = b""
        async for chunk in r.aiter_bytes():
            body += chunk
            if len(body) >= MAX_BYTES or b"</head>" in body.lower():
                break
        return r.status_code, url, body.decode(r.encoding or "utf-8", errors="replace")


async def verify(url: str, media: MediaList, client: httpx.AsyncClient) -> tuple[Article | None, str]:
    """(artículo verificado, motivo). El motivo explica por qué se descartó, si se descartó."""
    current = url
    for _ in range(MAX_HOPS):
        host = host_of(current)
        outlet = media.outlet_for(current)
        if not host:
            return None, "no es un enlace https"
        if outlet is None and host not in REDIRECTORS:
            return None, f"{host} no está en la lista de medios"
        try:
            status, nxt, page = await _download(client, current)
        except httpx.HTTPError as exc:
            return None, f"{host}: no se pudo descargar ({type(exc).__name__})"
        if nxt != current:
            current = nxt
            continue
        if status != 200 or outlet is None:
            return None, f"{host}: respondió {status}"
        headline = headline_from(page)
        try:
            return Article(headline, current, outlet), ""
        except MarketError:
            return None, f"{host}: la página no tiene un título usable"
    return None, "demasiadas redirecciones"


async def verify_all(urls: list[str], media: MediaList, trace: list[str], limit: int = 12) -> list[Article]:
    """Verifica en paralelo y deduplica por enlace final. Anota en la traza qué se descartó."""
    urls = list(dict.fromkeys(urls))[:limit]
    async with httpx.AsyncClient(timeout=6.0) as client:
        results = await asyncio.gather(*(verify(u, media, client) for u in urls))
    found: dict[str, Article] = {}
    rejected = []
    for article, why in results:
        if article and article.url not in found:
            found[article.url] = article
        elif why:
            rejected.append(why)
    trace.append(f"{len(urls)} enlace(s) candidatos → {len(found)} titular(es) verificados "
                 "en la página del medio")
    for why in rejected[:6]:
        trace.append(f"descartado: {why}")
    return list(found.values())
