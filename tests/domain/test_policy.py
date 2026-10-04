from app.domain.verdict import AcceptancePolicy, CensusPolicy, Proposal, Source

POLICY = AcceptancePolicy(min_confidence=0.8, min_sources=2)
TWO = [Source("k8s", "https://r/1", "kubernetes.io"), Source("gh", "https://r/2", "github.com")]


def decide(outcome, confidence, evidence=TWO):
    return POLICY.apply(Proposal.from_raw({"outcome": outcome, "confidence": confidence}), evidence, "m")


def test_accepts_confident_verdict_with_two_domains():
    assert decide("YES", 0.93).outcome == "YES"


def test_low_confidence_becomes_unresolved():
    assert decide("YES", 0.5).outcome == "UNRESOLVED"


def test_single_domain_becomes_unresolved():
    assert decide("NO", 0.99, TWO[:1]).outcome == "UNRESOLVED"


def test_two_sources_from_same_domain_count_once():
    same = [Source("a", "https://r/1", "github.com"), Source("b", "https://r/2", "github.com")]
    assert decide("YES", 0.99, same).outcome == "UNRESOLVED"


def test_no_grounding_at_all_becomes_unresolved():
    assert decide("YES", 1.0, []).outcome == "UNRESOLVED"


def test_invalid_outcome_fails_closed():
    assert decide("MAYBE", 1).outcome == "UNRESOLVED"


def test_garbage_confidence_is_zero():
    assert Proposal.from_raw({"outcome": "yes", "confidence": "mucha"}).confidence == 0.0


def test_thresholds_are_configurable():
    lax = AcceptancePolicy(min_confidence=0.5, min_sources=1)
    assert lax.apply(Proposal("NO", 0.6, ""), TWO[:1], "m").outcome == "NO"


def test_census_majority_resolves():
    assert CensusPolicy(5).tally([True] * 4 + [False] * 2, 0.5).outcome == "YES"


def test_census_exact_threshold_is_no():
    assert CensusPolicy(2).tally([True, False], 0.5).outcome == "NO"


def test_census_below_minimum_fails_closed():
    assert CensusPolicy(5).tally([True] * 4, 0.5).outcome == "UNRESOLVED"
