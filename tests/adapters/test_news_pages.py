import asyncio
import json

import httpx
import pytest

from app.adapters.news import media_list
from app.adapters.news.mock import REHEARSAL, MockNewsDesk, MockNewsReader
from app.adapters.news.pages import headline_from, verify
from app.adapters.news.vertex import VertexNewsDesk
from app.domain.media import MediaList, Outlet

LEFT = Outlet("Medio A", "medio-a.test", "izquierda", "lista del ponente")
RIGHT = Outlet("Medio B", "medio-b.test", "derecha", "lista del ponente")
MEDIA = MediaList((LEFT, RIGHT))
PAGE = ('<html><head><title>Sitio | Medio A</title>'
        '<meta property="og:title" content="La tasa sube &amp; baja">')


def client(routes):
    def handler(request):
        return routes.get(str(request.url), httpx.Response(404))
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_headline_prefers_og_title_and_unescapes():
    assert headline_from(PAGE) == "La tasa sube & baja"
    assert headline_from("<title>\n  Solo   título </title>") == "Solo título"


def test_verified_article_uses_the_page_title_not_the_model():
    c = client({"https://medio-a.test/1": httpx.Response(200, html=PAGE)})
    article, _ = asyncio.run(verify("https://medio-a.test/1", MEDIA, c))
    assert article.headline == "La tasa sube & baja" and article.outlet is LEFT


def test_outlets_off_the_list_are_never_downloaded():
    called = []

    def handler(request):
        called.append(request.url)
        return httpx.Response(200, html=PAGE)

    c = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    article, why = asyncio.run(verify("https://otro.test/1", MEDIA, c))
    assert article is None and "no está en la lista" in why and called == []


def test_redirect_off_the_list_is_rejected():
    c = client({"https://medio-a.test/1": httpx.Response(302, headers={"location": "https://otro.test/x"})})
    article, why = asyncio.run(verify("https://medio-a.test/1", MEDIA, c))
    assert article is None and "otro.test" in why


def test_grounding_redirector_is_followed_to_the_outlet():
    hop = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    c = client({hop: httpx.Response(302, headers={"location": "https://www.medio-b.test/n"}),
                "https://www.medio-b.test/n": httpx.Response(200, html=PAGE)})
    article, _ = asyncio.run(verify(hop, MEDIA, c))
    assert article.outlet is RIGHT and article.url == "https://www.medio-b.test/n"


def test_redirector_alone_is_not_an_article():
    hop = "https://vertexaisearch.cloud.google.com/x"
    article, _ = asyncio.run(verify(hop, MEDIA, client({hop: httpx.Response(200, html=PAGE)})))
    assert article is None


def test_mock_desk_never_puts_words_in_real_outlets_mouths():
    find = asyncio.run(MockNewsDesk().find("tasa", MEDIA))
    assert {a.outlet.domain for a in find.articles} <= {o.domain for o in REHEARSAL.outlets}
    assert all(a.outlet.domain.endswith(".example") and "[Ensayo]" in a.headline for a in find.articles)


def test_mock_readers_split_by_diet():
    find = asyncio.run(MockNewsDesk().find("tasa", MEDIA))
    left = [a for a in find.articles if a.outlet.lean == "izquierda"]
    right = [a for a in find.articles if a.outlet.lean == "derecha"]
    r = MockNewsReader()
    pl, pr, pb = (asyncio.run(r.estimate("¿q?", "c", x)).p for x in (left, right, find.articles))
    assert pl != pr and pb == pytest.approx(0.5)


def test_media_list_loads_and_missing_file_is_empty(tmp_path):
    f = tmp_path / "medios.json"
    f.write_text(json.dumps({"fuente": "mi criterio", "medios": [
        {"nombre": "A", "dominio": "WWW.A.test", "inclinacion": "izquierda", "fuente": "x"},
        {"nombre": "B", "dominio": "b.test", "inclinacion": "derecha", "fuente": "y"}]}))
    m = media_list.load(f)
    assert m.ready and m.outlets[0].domain == "a.test" and m.source == "mi criterio"
    assert media_list.load(tmp_path / "no.json") == MediaList()


def test_shipped_media_list_is_empty_until_the_presenter_fills_it():
    from app.config import DEFAULT_MEDIA
    assert not media_list.load(DEFAULT_MEDIA).ready


class FakeClient:
    model, location = "m", "global"

    def __init__(self, payload):
        self.payload = payload

    async def generate(self, body, timeout=90):
        self.body = body
        return self.payload


def test_vertex_desk_fails_closed_on_prose(monkeypatch):
    payload = {"candidates": [{"content": {"parts": [{"text": "no sé"}]}}]}
    find = asyncio.run(VertexNewsDesk(FakeClient(payload)).find("tasa", MEDIA))
    assert find.raw is None and find.articles == []
