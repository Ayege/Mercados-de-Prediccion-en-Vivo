"""Busca titulares en el RSS de búsqueda de Google News, solo en los medios de la lista.

Google News atribuye cada titular a su medio con `<source url="…">`. Ese es el
dato que decide a qué medio pertenece: nunca el texto del modelo. Un titular
cuyo medio no está en la lista se descarta.

Solo se descarga `news.google.com`, por https, con límite de tiempo y tamaño.
El XML se lee con expresiones regulares, no con un parser con entidades.
"""
from __future__ import annotations

import asyncio
import html
import re

import httpx

from ...domain.errors import MarketError
from ...domain.media import LEANS, Article, MediaList

SEARCH = "https://news.google.com/rss/search"
MAX_BYTES = 1_000_000
ITEM = re.compile(r"<item>(.*?)</item>", re.S)
FIELD = {k: re.compile(rf"<{k}>(.*?)</{k}>", re.S) for k in ("title", "link")}
SOURCE = re.compile(r'<source url="([^"]+)">(.*?)</source>', re.S)


def _text(raw: str) -> str:
    raw = raw.strip().removeprefix("<![CDATA[").removesuffix("]]>")
    return " ".join(html.unescape(raw).split())


def parse(feed: str, media: MediaList) -> list[Article]:
    out = []
    for item in ITEM.findall(feed):
        title, link, source = FIELD["title"].search(item), FIELD["link"].search(item), SOURCE.search(item)
        if not (title and link and source):
            continue
        outlet = media.outlet_for(_text(source.group(1)))
        if outlet is None:
            continue
        headline = _text(title.group(1))
        suffix = " - " + _text(source.group(2))
        headline = headline.removesuffix(suffix).strip()
        try:
            out.append(Article(headline, _text(link.group(1)), outlet, via="Google News"))
        except MarketError:
            continue
    return out


async def _fetch(client: httpx.AsyncClient, query: str) -> str:
    params = {"q": query, "hl": "es-419", "gl": "US", "ceid": "US:es-419"}
    async with client.stream("GET", SEARCH, params=params, follow_redirects=False) as r:
        r.raise_for_status()
        body = b""
        async for chunk in r.aiter_bytes():
            body += chunk
            if len(body) >= MAX_BYTES:
                break
        return body.decode("utf-8", errors="replace")


async def search(topic: str, media: MediaList, trace: list[str], per_side: int = 8,
                 client: httpx.AsyncClient | None = None) -> list[Article]:
    """Una búsqueda por lado, de los últimos 7 días. Nunca lanza: un lado que falla queda vacío."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=8.0)
    try:
        async def side(lean: str) -> list[Article]:
            sites = " OR ".join(f"site:{o.domain}" for o in media.outlets if o.lean == lean)
            try:
                found = parse(await _fetch(client, f"{topic} ({sites}) when:7d"), media)
            except httpx.HTTPError as exc:
                trace.append(f"Google News ({lean}): falló la búsqueda ({type(exc).__name__})")
                return []
            found = [a for a in found if a.outlet.lean == lean][:per_side]
            trace.append(f"Google News ({lean}): {len(found)} titular(es) de "
                         f"{', '.join(sorted({a.outlet.name for a in found})) or 'ningún medio de la lista'}")
            return found

        results = await asyncio.gather(*(side(lean) for lean in LEANS))
    finally:
        if own:
            await client.aclose()
    seen, out = set(), []
    for a in (a for r in results for a in r):
        if a.headline not in seen:
            seen.add(a.headline)
            out.append(a)
    return out
