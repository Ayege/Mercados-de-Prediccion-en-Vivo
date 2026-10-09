"""Preguntas desde las noticias, con editor y lectores falsos."""
import asyncio

import pytest

from app.adapters.memory import InMemoryRepository
from app.application.errors import Cooldown
from app.application.news import NewsService
from app.application.service import MarketService
from app.domain.errors import MarketError
from app.domain.media import Article, Estimate, MediaList, NewsFind, Outlet

LEFT = Outlet("Medio A", "medio-a.test", "izquierda", "lista del ponente")
RIGHT = Outlet("Medio B", "medio-b.test", "derecha", "lista del ponente")
MEDIA = MediaList((LEFT, RIGHT), source="lista del ponente")
RAW = {"pregunta": "¿Subirá la tasa antes del viernes?", "criterio": "SÍ si el banco central lo publica.",
       "tipo": "futuro"}
ARTICLES = [Article("La izquierda dice que sí subirá", "https://medio-a.test/1", LEFT),
            Article("La derecha dice que no subirá", "https://medio-b.test/1", RIGHT)]


class Desk:
    name = model = "fake"

    def __init__(self, raw=RAW, articles=ARTICLES):
        self.raw, self.articles, self.calls = raw, articles, 0

    async def find(self, topic, media):
        self.calls += 1
        return NewsFind(self.raw, list(self.articles), ["fake"], "fake")


class Reader:
    """Cree lo que dicen sus titulares: izquierda empuja al SÍ, derecha al NO."""

    name = model = "fake"

    def __init__(self):
        self.seen = []

    async def estimate(self, question, criteria, articles):
        self.seen.append(sorted(a.outlet.lean for a in articles))
        p = 0.5 + sum(0.3 if a.outlet.lean == "izquierda" else -0.3 for a in articles)
        return Estimate(p, "fake")


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


def news(desk=None, reader=None, media=MEDIA, clock=None):
    markets = MarketService(InMemoryRepository(), oracle=None, oracle_cooldown=0)
    return NewsService(markets, markets.repo, desk or Desk(), reader or Reader(), media,
                       clock=clock or Clock(), cooldown=30)


def opened(n):
    d = asyncio.run(n.propose("tasa de interés"))
    return n.open(d["id"])["id"]


def test_without_a_media_list_nothing_is_searched():
    desk = Desk()
    with pytest.raises(MarketError, match="lista de medios"):
        asyncio.run(news(desk, media=MediaList()).propose("tasa"))
    assert desk.calls == 0


def test_searches_are_rate_limited():
    clock = Clock()
    n = news(clock=clock)
    asyncio.run(n.propose("tasa"))
    with pytest.raises(Cooldown):
        asyncio.run(n.propose("tasa"))
    clock.now += 31
    asyncio.run(n.propose("tasa"))


def test_a_rejected_draft_cannot_be_opened():
    n = news(Desk(articles=ARTICLES[:1]))
    d = asyncio.run(n.propose("tasa"))
    assert not d["accepted"]
    with pytest.raises(MarketError):
        n.open(d["id"])


def test_opening_creates_a_market_with_its_coverage_once():
    n = news()
    d = asyncio.run(n.propose("tasa"))
    m = n.open(d["id"])
    assert m["topic"] == "tasa" and m["coverage_count"] == {"izquierda": 1, "derecha": 1}
    assert m["prices"]["YES"] == 0.5
    with pytest.raises(MarketError):
        n.open(d["id"])


def test_each_agent_reads_its_diet_and_trades_toward_its_belief():
    reader = Reader()
    n = news(reader=reader)
    mid = opened(n)
    m = asyncio.run(n.consult_agents(mid))
    assert set(map(tuple, reader.seen)) == {(), ("derecha",), ("izquierda",), ("derecha", "izquierda")}
    by = {a["diet"]: a for a in m["agents"]}
    assert by["izquierda"]["p"] == 0.8 and by["izquierda"]["outcome"] == "YES"
    assert by["derecha"]["p"] == 0.2 and by["derecha"]["outcome"] == "NO"
    assert m["volume"] > 0


def test_agents_opine_once_per_question():
    n = news()
    mid = opened(n)
    asyncio.run(n.consult_agents(mid))
    with pytest.raises(MarketError):
        asyncio.run(n.consult_agents(mid))


def test_agents_only_read_news_questions():
    n = news()
    mid = n.markets.create("¿Pregunta normal?", "Criterio")["id"]
    with pytest.raises(MarketError):
        asyncio.run(n.consult_agents(mid))


def test_agent_that_cannot_read_does_not_bet():
    class Broken(Reader):
        async def estimate(self, question, criteria, articles):
            return Estimate(None, "")

    n = news(reader=Broken())
    m = asyncio.run(n.consult_agents(opened(n)))
    assert all(a["outcome"] is None for a in m["agents"]) and m["volume"] == 0


def test_resolution_shows_which_diet_made_money():
    class Yes:
        name = model = "fake"

        async def resolve(self, query):
            from app.domain.verdict import Verdict
            return Verdict("YES", 1.0, "", trace=["fake"])

    n = news()
    n.markets.oracle = Yes()
    mid = opened(n)
    asyncio.run(n.consult_agents(mid))
    m = asyncio.run(n.markets.resolve(mid))
    by = {a["diet"]: a for a in m["agents"]}
    assert by["izquierda"]["pnl"] > 0 > by["derecha"]["pnl"]


def test_agents_cannot_be_used_from_outside():
    n = news()
    asyncio.run(n.consult_agents(opened(n)))
    from app.application.errors import Unauthorized
    with pytest.raises(Unauthorized):
        n.markets.account("agente:izquierda", "")


# --- la sala también tiene dieta de medios ------------------------------------------------
def test_the_room_is_split_by_side_and_each_phone_sees_only_its_side():
    n = news()
    entered = [n.markets.enter(name) for name in ("ana", "beto", "caro", "dani")]  # antes de la pregunta
    mid = opened(n)
    late = n.markets.enter("eva")  # después de la pregunta
    sides = []
    for e in [*entered, late]:
        diet = n.markets.account(e["name"], e["token"])["diets"][mid]
        assert diet["side"] in ("izquierda", "derecha")
        assert {a["lean"] for a in diet["articles"]} == {diet["side"]}
        sides.append(diet["side"])
    assert abs(sides.count("izquierda") - sides.count("derecha")) <= 1


def test_room_bets_are_counted_by_side_and_agent_bets_are_not():
    n = news()
    mid = opened(n)
    e = n.markets.enter("ana")
    side = n.markets.account("ana", e["token"])["diets"][mid]["side"]
    n.markets.trade(mid, "ana", e["token"], "YES", 50)
    asyncio.run(n.consult_agents(mid))
    groups = n.markets.view(mid)["diet"]["groups"]
    assert groups[side]["traders"] == 1 and groups[side]["yes_share"] == 1.0
    other = "derecha" if side == "izquierda" else "izquierda"
    assert groups[other]["traders"] == 0


def test_the_projection_hides_headlines_and_reasoning_until_revealed():
    n = news()
    mid = opened(n)
    m = asyncio.run(n.consult_agents(mid))
    assert m["coverage"] == [] and not m["diet"]["revealed"]
    assert all(a["read"] == [] and a["reasoning"] == "" for a in m["agents"])
    assert {a["diet"]: a["read_count"] for a in m["agents"]}["ambas"] == 2
    m = n.markets.reveal(mid)
    assert len(m["coverage"]) == 2 and all(a["reasoning"] for a in m["agents"])
