import pytest

from app.domain.errors import MarketError
from app.domain.framing import Exposure, Framing, FramingPolicy, Headline
from app.domain.market import Market
from app.domain.verdict import Verdict

FRAMING = Framing(Headline("Todo va según el calendario", "titular de ensayo"),
                  Headline("Advierten que la fecha puede moverse", "titular de ensayo"))


def verdict(outcome, confidence=0.9):
    return Verdict(outcome, confidence, "", trace=["neutral"])


def test_block_randomization_keeps_groups_within_one_person():
    e = Exposure()
    for i in range(41):
        e.assign(f"p{i}", "m1")
        sizes = [sum(1 for a in e.arms.values() if a == arm) for arm in ("pro_si", "pro_no")]
        assert abs(sizes[0] - sizes[1]) <= 1


def test_a_person_always_sees_the_same_headline():
    e = Exposure()
    first = e.assign("aye", "m1")
    for i in range(10):
        e.assign(f"p{i}", "m1")
    assert e.assign("aye", "m1") == first


def test_summary_reports_only_group_aggregates():
    e = Exposure()
    a, b = e.assign("aye", "m1"), e.assign("bob", "m1")
    assert a != b
    e.record("aye", "YES", 30)
    e.record("aye", "NO", 10)
    s = e.summary()
    assert s[a] == {"exposed": 1, "traders": 1, "yes_share": 0.75}
    assert s[b] == {"exposed": 1, "traders": 0, "yes_share": None}
    assert "aye" not in str(s)


def test_headline_needs_a_source_and_https():
    with pytest.raises(MarketError):
        Headline("Un titular sin fuente", " ")
    with pytest.raises(MarketError):
        Headline("Un titular con enlace inseguro", "medio", "http://medio.test")


def test_only_oracle_questions_can_be_framed():
    with pytest.raises(MarketError):
        Market("m", "¿Pregunta?", "Criterio", kind="sala", framing=FRAMING)


def test_buying_records_the_buyers_group():
    m = Market("m", "¿Pregunta?", "Criterio", framing=FRAMING)
    m.buy("YES", 50, "aye")
    arm = m.exposure.arms["aye"]
    assert m.exposure.summary()[arm]["yes_share"] == 1.0


def test_unframed_market_ignores_the_buyer():
    m = Market("m", "¿Pregunta?", "Criterio")
    m.buy("YES", 50, "aye")
    assert m.exposure.arms == {} and m.headline_for("aye") is None


def test_framing_policy_accepts_a_verdict_that_does_not_depend_on_the_headline():
    framed = {"pro_si": verdict("YES", 0.95), "pro_no": verdict("YES", 0.82)}
    v = FramingPolicy().apply(verdict("YES"), framed)
    assert v.outcome == "YES"
    assert v.framing["pro_no"] == {"outcome": "YES", "confidence": 0.82}
    assert "no depende del titular" in v.trace[-1]


def test_framing_policy_fails_closed_when_the_headline_flips_the_verdict():
    neutral = verdict("YES")
    v = FramingPolicy().apply(neutral, {"pro_si": verdict("YES"), "pro_no": verdict("NO")})
    assert v.outcome == "UNRESOLVED" and "pro-no" in v.trace[-1]
    assert neutral.outcome == "YES"  # no muta la lectura neutral


def test_framing_policy_treats_a_lost_nerve_as_a_flip():
    framed = {"pro_si": verdict("UNRESOLVED", 0.0), "pro_no": verdict("NO")}
    v = FramingPolicy().apply(verdict("NO"), framed)
    assert v.outcome == "UNRESOLVED"


def test_framing_policy_leaves_an_undecided_neutral_alone():
    neutral = verdict("UNRESOLVED", 0.0)
    assert FramingPolicy().apply(neutral, {}) is neutral
