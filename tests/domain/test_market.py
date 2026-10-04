import pytest

from app.domain.errors import MarketError
from app.domain.market import Account, Market
from app.domain.verdict import Verdict


def test_unknown_kind_is_rejected():
    with pytest.raises(MarketError):
        Market("m", "¿q?", "c", kind="pasado")


def test_buy_moves_price_and_history():
    m = Market("m", "¿q?", "c")
    m.buy("YES", 50)
    assert m.prices()["YES"] > 0.5 and len(m.history) == 2


@pytest.mark.parametrize("outcome,spend", [("MAYBE", 10), ("YES", 0), ("YES", 10_001)])
def test_invalid_orders_do_not_touch_state(outcome, spend):
    m = Market("m", "¿q?", "c")
    with pytest.raises(MarketError):
        m.buy(outcome, spend)
    assert m.q == [0.0, 0.0] and m.history == [0.5]


def test_unresolved_verdict_keeps_market_open():
    m = Market("m", "¿q?", "c")
    assert m.record(Verdict("UNRESOLVED", 0, ""), 0.5, None, 0) is False
    assert m.status == "open" and len(m.attempts) == 1


def test_decisive_verdict_closes_market():
    m = Market("m", "¿q?", "c")
    assert m.record(Verdict("NO", 1, ""), 0.7, None, 0) is True
    with pytest.raises(MarketError):
        m.buy("YES", 10)


def test_census_only_on_room_markets():
    with pytest.raises(MarketError):
        Market("m", "¿q?", "c").answer_census("aye", True)


def test_account_settles_one_credit_per_winning_share():
    a = Account("aye", 100)
    a.add_shares("m", "YES", 30)
    a.add_shares("m", "NO", 5)
    a.settle("m", "YES")
    assert a.balance == 130
