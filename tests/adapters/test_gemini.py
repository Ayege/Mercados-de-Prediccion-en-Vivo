import asyncio

import pytest

from app.adapters.oracle.gemini import inject_fault, interpret, normalize_sources, parse_verdict, run
from app.adapters.oracle.mock import MockOracle
from app.adapters.oracle.vertex import VertexOracle
from app.application.ports import FAULTS
from app.domain.framing import Framing, Headline
from app.domain.verdict import AcceptancePolicy

POLICY = AcceptancePolicy()

CHUNKS = [
    {"web": {"uri": "https://redirect.test/1", "title": "kubernetes.io", "domain": "kubernetes.io"}},
    {"web": {"uri": "https://redirect.test/2", "title": "github.com", "domain": "github.com"}},
]
TWO = normalize_sources(CHUNKS)


def test_parse_verdict_ignores_surrounding_text():
    assert parse_verdict('ok {"outcome": "YES"} fin')["outcome"] == "YES"


def test_parse_verdict_rejects_non_json():
    with pytest.raises(ValueError):
        parse_verdict("no hay json")


def test_redirect_uris_do_not_collapse_domains():
    # Los dos chunks comparten host en la uri; el dominio real los distingue.
    assert {e.domain for e in TWO} == {"kubernetes.io", "github.com"}


def test_domain_falls_back_to_title():
    src = normalize_sources([{"web": {"uri": "https://redirect.test/3", "title": "WWW.Python.org"}}])
    assert src[0].domain == "python.org"


def test_chunk_without_domain_or_title_is_dropped():
    assert normalize_sources([{"web": {"uri": "https://redirect.test/4"}}]) == []


def test_non_https_chunk_is_dropped():
    assert normalize_sources([{"web": {"uri": "http://x.test", "domain": "x.test"}}]) == []


# --- fallos inyectados: misma ruta que Vertex AI ----------------------------

GOOD = {"candidates": [{
    "content": {"parts": [{"text": '{"outcome": "NO", "confidence": 0.95, "reasoning": "r"}'}]},
    "groundingMetadata": {"groundingChunks": CHUNKS, "webSearchQueries": ["q"]},
}]}


def test_clean_payload_is_accepted():
    assert interpret(inject_fault(GOOD, None, []), "m", [], POLICY).outcome == "NO"


@pytest.mark.parametrize("fault", ["baja_confianza", "un_dominio", "json_malformado"])
def test_each_payload_fault_is_rejected_by_policy(fault):
    trace = []
    v = interpret(inject_fault(GOOD, fault, trace), "m", trace, POLICY)
    assert v.outcome == "UNRESOLVED"
    assert any(fault in line for line in v.trace)


def test_fault_injection_does_not_mutate_original():
    inject_fault(GOOD, "json_malformado", [])
    assert "outcome" in GOOD["candidates"][0]["content"]["parts"][0]["text"]


@pytest.mark.parametrize("fault", list(FAULTS))
def test_mock_oracle_fails_closed_for_every_fault(fault, monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "YES")
    v = asyncio.run(MockOracle().resolve("¿x?", "c", fault))
    assert v.outcome == "UNRESOLVED"


def test_network_down_never_calls_the_model():
    called = []

    async def call(q, c, news=None):
        called.append(q)
        return GOOD

    v = asyncio.run(run(call, "¿x?", "c", "m", [], POLICY, "red_caida"))
    assert v.outcome == "UNRESOLVED" and called == []


def test_unknown_fault_is_rejected():
    with pytest.raises(ValueError):
        asyncio.run(MockOracle().resolve("¿x?", "c", "meteorito"))


# --- titulares: cómo le llegan al modelo --------------------------------------

NEWS = Framing(Headline("Todo va según el calendario", "titular de ensayo"),
               Headline("Advierten que la fecha puede moverse", "titular de ensayo")).news()


def test_mock_oracle_ignores_untrusted_news(monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "YES")
    v = asyncio.run(MockOracle().resolve("¿x?", "c", None, NEWS["pro_no"]))
    assert v.outcome == "YES"
    assert any("dato no confiable" in line for line in v.trace)


def test_mock_oracle_believes_trusted_news(monkeypatch):
    monkeypatch.setenv("ORACLE_MOCK_FORCE", "YES")
    trusted = Framing(Headline("Todo va según el calendario", "e"),
                      Headline("Advierten que la fecha puede moverse", "e")).news(trusted=True)
    assert asyncio.run(MockOracle().resolve("¿x?", "c", None, trusted["pro_no"])).outcome == "NO"


class FakeClient:
    model, location = "m", "global"

    def __init__(self):
        self.payloads = []

    async def generate(self, payload):
        self.payloads.append(payload)
        return GOOD


def test_vertex_puts_untrusted_news_in_the_user_turn():
    client = FakeClient()
    asyncio.run(VertexOracle(client, POLICY).resolve("¿x?", "c", None, NEWS["pro_si"]))
    p = client.payloads[0]
    assert "<noticia" in p["contents"][0]["parts"][0]["text"]
    assert "Todo va según" not in p["systemInstruction"]["parts"][0]["text"]


def test_vertex_trusted_news_fault_promotes_the_headline_to_system():
    client = FakeClient()
    trusted = Framing(NEWS["pro_si"].headline, NEWS["pro_no"].headline).news(trusted=True)
    asyncio.run(VertexOracle(client, POLICY).resolve("¿x?", "c", None, trusted["pro_no"]))
    system = client.payloads[0]["systemInstruction"]["parts"][0]["text"]
    assert "NOTICIA VERIFICADA" in system and "Advierten" in system
