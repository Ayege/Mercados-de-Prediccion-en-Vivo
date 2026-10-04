import pytest

from app.oracle import apply_policy, normalize_sources, parse_verdict

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
    assert {e["domain"] for e in TWO} == {"kubernetes.io", "github.com"}


def test_domain_falls_back_to_title():
    src = normalize_sources([{"web": {"uri": "https://redirect.test/3", "title": "WWW.Python.org"}}])
    assert src[0]["domain"] == "python.org"


def test_chunk_without_domain_or_title_is_dropped():
    assert normalize_sources([{"web": {"uri": "https://redirect.test/4"}}]) == []


def test_non_https_chunk_is_dropped():
    assert normalize_sources([{"web": {"uri": "http://x.test", "domain": "x.test"}}]) == []


def test_accepts_confident_verdict_with_two_domains():
    assert apply_policy({"outcome": "YES", "confidence": 0.93}, TWO, "m").outcome == "YES"


def test_low_confidence_becomes_unresolved():
    assert apply_policy({"outcome": "YES", "confidence": 0.5}, TWO, "m").outcome == "UNRESOLVED"


def test_single_domain_becomes_unresolved():
    one = normalize_sources([CHUNKS[0]])
    assert apply_policy({"outcome": "NO", "confidence": 0.99}, one, "m").outcome == "UNRESOLVED"


def test_no_grounding_at_all_becomes_unresolved():
    assert apply_policy({"outcome": "YES", "confidence": 1.0}, [], "m").outcome == "UNRESOLVED"


def test_invalid_outcome_fails_closed():
    assert apply_policy({"outcome": "MAYBE", "confidence": 1}, TWO, "m").outcome == "UNRESOLVED"
