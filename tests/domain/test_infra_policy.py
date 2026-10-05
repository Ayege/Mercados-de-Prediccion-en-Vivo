"""La política que separa una decisión de una llamada a una cuenta real de Google Cloud."""

from app.domain.cloud.infra import Action, ActuationPolicy, NodeSpec, NodeState, distribute, plan

POLICY = ActuationPolicy(
    max_total_min=3,
    max_min_per_region=1,
    max_max_per_region=3,
    max_services=3,
    max_calls_per_cycle=3,
    seconds_between_changes=60,
)


def test_distribute_follows_replica_weights():
    d = distribute({"us-east1": 3, "us-central1": 1}, 2)
    assert sum(s.min_instances for s in d.values()) == 2
    assert d["us-east1"].min_instances >= d["us-central1"].min_instances
    assert d["us-east1"].max_instances == 3


def test_distribute_never_exceeds_replicas():
    d = distribute({"us-east1": 1}, 5)
    assert d["us-east1"] == NodeSpec(1, 1)


def test_clamp_drops_unknown_regions_and_caps_instances():
    desired, notes = POLICY.clamp({"marte-1": NodeSpec(1, 1), "us-east1": NodeSpec(2, 9)})
    assert desired == {"us-east1": NodeSpec(1, 3)}
    assert any("marte-1" in n for n in notes) and any("recortado" in n for n in notes)


def test_clamp_enforces_total_minimum():
    regions = ["us-east1", "us-central1", "europe-west1", "southamerica-east1"]
    desired, _ = ActuationPolicy(max_total_min=2).clamp({r: NodeSpec(1, 2) for r in regions})
    assert sum(s.min_instances for s in desired.values()) == 2


def test_plan_creates_scales_and_deletes():
    actual = {
        "us-east1": NodeState("us-east1", ready=True, min_instances=0, max_instances=1),
        "europe-west1": NodeState("europe-west1", ready=True),
    }
    desired = {"us-east1": NodeSpec(1, 2), "us-central1": NodeSpec(0, 1)}
    kinds = {(a.kind, a.region) for a in plan(desired, actual, "x")}
    assert kinds == {("escalar", "us-east1"), ("crear", "us-central1"), ("borrar", "europe-west1")}


def check(actions, actual=None, last=None, now=1000.0):
    return [(r.allowed, r.why) for r in POLICY.check(actions, actual or {}, last or {}, now)]


def test_check_rejects_region_outside_allowlist():
    assert check([Action("crear", "marte-1", 0, 1)]) == [(False, "región no permitida")]


def test_check_rejects_touching_a_service_while_it_reconciles():
    actual = {"us-east1": NodeState("us-east1", reconciling=True, min_instances=0, max_instances=1)}
    assert check([Action("escalar", "us-east1", 1, 2)], actual)[0][0] is False


def test_check_rate_limits_scaling_but_not_repairs():
    actual = {"us-east1": NodeState("us-east1", ready=True, min_instances=0, max_instances=1)}
    last = {"us-east1": 990.0}
    out = check([Action("escalar", "us-east1", 1, 2), Action("reparar", "us-east1")], actual, last)
    assert out[0][0] is False and "60 s" in out[0][1]
    assert out[1][0] is True


def test_check_caps_calls_per_cycle():
    actions = [
        Action("crear", r, 0, 1) for r in ("us-east1", "us-central1", "europe-west1", "southamerica-east1")
    ]
    allowed = [ok for ok, _ in check(actions)]
    assert allowed.count(True) == 3


def test_check_caps_total_minimum_instances_across_actions():
    actions = [Action("crear", r, 1, 1) for r in ("us-east1", "us-central1", "europe-west1")]
    out = check(actions, now=0)
    assert [ok for ok, _ in out] == [True, True, True]
    out = POLICY.check(
        [Action("crear", "southamerica-east1", 1, 1)],
        {r: NodeState(r, min_instances=1, max_instances=1) for r in ("us-east1", "us-central1")},
        {},
        0,
    )
    assert out[0].allowed is True  # 3 de 3
    full = {
        r: NodeState(r, min_instances=1, max_instances=1) for r in ("us-east1", "us-central1", "europe-west1")
    }
    assert POLICY.check([Action("escalar", "us-east1", 1, 2)], full, {}, 0)[0].allowed is True
    assert POLICY.check([Action("crear", "southamerica-east1", 1, 1)], full, {}, 0)[0].allowed is False


def test_check_rejects_unknown_fault():
    actual = {"us-east1": NodeState("us-east1", ready=True)}
    assert check([Action("falla", "us-east1", fault="meteorito")], actual)[0][0] is False
