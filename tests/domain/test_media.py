import pytest

from app.domain import lmsr
from app.domain.errors import MarketError
from app.domain.media import (
    AGENTS,
    Article,
    MediaList,
    NewsFind,
    NewsPolicy,
    Outlet,
    read_for,
    stake_for,
)

LEFT = Outlet("Medio A", "medio-a.test", "izquierda", "lista del ponente")
RIGHT = Outlet("Medio B", "medio-b.test", "derecha", "lista del ponente")
MEDIA = MediaList((LEFT, RIGHT), source="lista del ponente")
RAW = {"pregunta": "¿Subirá la tasa antes del viernes?", "criterio": "SÍ si el banco central lo publica.",
       "tipo": "futuro"}


def art(outlet, n=1):
    return Article(f"Titular número {n} del medio", f"https://{outlet.domain}/nota-{n}", outlet)


def test_outlet_needs_a_known_lean_a_domain_and_a_source():
    with pytest.raises(MarketError):
        Outlet("X", "x.test", "centro", "s")
    with pytest.raises(MarketError):
        Outlet("X", "no es dominio", "izquierda", "s")
    with pytest.raises(MarketError):
        Outlet("X", "x.test", "izquierda", " ")


def test_list_matches_subdomains_but_not_lookalikes():
    assert MEDIA.outlet_for("https://www.medio-a.test/x") is LEFT
    assert MEDIA.outlet_for("https://noticias.medio-a.test/x") is LEFT
    assert MEDIA.outlet_for("https://medio-a.test.evil.test/x") is None
    assert MEDIA.outlet_for("http://medio-a.test/x") is None


def test_list_is_ready_only_with_both_sides():
    assert MEDIA.ready and not MediaList((LEFT,)).ready and not MediaList().ready


def test_article_must_live_on_its_outlet():
    with pytest.raises(MarketError):
        Article("Titular atribuido a otro medio", "https://medio-b.test/x", LEFT)


def test_policy_accepts_a_question_with_both_sides():
    d = NewsPolicy().check("d1", "tasa", NewsFind(RAW, [art(LEFT), art(RIGHT)], []))
    assert d.accepted and d.kind == "futuro"


@pytest.mark.parametrize("raw, articles, why", [
    (None, [art(LEFT), art(RIGHT)], "no propuso"),
    ({**RAW, "pregunta": "Una afirmación"}, [art(LEFT), art(RIGHT)], "sí o no"),
    ({**RAW, "tipo": "opinion"}, [art(LEFT), art(RIGHT)], "tipo inválido"),
    (RAW, [art(LEFT), art(LEFT, 2)], "de derecha"),
])
def test_policy_fails_closed(raw, articles, why):
    d = NewsPolicy().check("d1", "tasa", NewsFind(raw, articles, []))
    assert not d.accepted and any(why in t for t in d.trace)


def test_policy_caps_articles_per_side():
    find = NewsFind(RAW, [art(LEFT, n) for n in range(5)] + [art(RIGHT)], [])
    d = NewsPolicy(max_per_side=2).check("d1", "t", find)
    assert sum(a.outlet is LEFT for a in d.articles) == 2


def test_each_diet_reads_only_its_side():
    coverage = [art(LEFT), art(RIGHT)]
    assert read_for("izquierda", coverage) == [coverage[0]]
    assert read_for("derecha", coverage) == [coverage[1]]
    assert read_for("ambas", coverage) == coverage
    assert read_for("ninguna", coverage) == []
    assert set(AGENTS.values()) == {"izquierda", "derecha", "ambas", "ninguna"}


def test_agent_buys_until_the_price_reaches_its_belief():
    q, b = [0.0, 0.0], 100.0
    outcome, spend = stake_for(0.7, q, b, budget=1000)
    assert outcome == "YES"
    q[0] += lmsr.shares_for_spend(q, b, 0, spend)
    assert lmsr.prices(q, b)[0] == pytest.approx(0.7, abs=1e-3)


def test_agent_bets_no_when_it_believes_less_than_the_price():
    q, b = [0.0, 0.0], 100.0
    outcome, spend = stake_for(0.2, q, b, budget=1000)
    q[1] += lmsr.shares_for_spend(q, b, 1, spend)
    assert outcome == "NO" and lmsr.prices(q, b)[0] == pytest.approx(0.2, abs=1e-3)


def test_agent_respects_its_budget_and_skips_small_edges():
    assert stake_for(0.99, [0.0, 0.0], 100.0, budget=50) == ("YES", 50.0)
    assert stake_for(0.52, [0.0, 0.0], 100.0, budget=50) == (None, 0.0)
    assert stake_for(None, [0.0, 0.0], 100.0, budget=50) == (None, 0.0)
