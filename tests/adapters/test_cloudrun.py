"""El adaptador de Cloud Run sin red: se verifica qué pediría a la Admin API v2."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.infra.cloudrun import CloudRunNodeGateway
from app.node import app as node_app


class Recorder(CloudRunNodeGateway):
    def __init__(self, responses=None, **kw):
        super().__init__("proj", "img:1", "nodo@proj.iam.gserviceaccount.com", **kw)
        self.sent = []
        self.responses = responses or {}

    async def _request(self, method, url, **kw):
        params = kw.get("params", {})
        if self.validate_only and method != "GET":
            params = {**params, "validateOnly": "true"}
        self.sent.append((method, url, params, kw.get("json")))
        status, body = self.responses.get((method, url.rsplit("/", 1)[-1]), (404, {}))
        return httpx.Response(status, json=body, request=httpx.Request(method, url))


OWN = {
    "labels": {"oraculo-demo": "true"},
    "uri": "https://n.run.app",
    "etag": "e1",
    "reconciling": False,
    "terminalCondition": {"state": "CONDITION_SUCCEEDED"},
    "latestReadyRevision": "x/revisions/r7",
    "template": {
        "scaling": {"minInstanceCount": 1, "maxInstanceCount": 2},
        "containers": [{"env": [{"name": "NODO_FALLA", "value": "latencia"}]}],
    },
}


def test_create_targets_only_prefixed_services_with_labels():
    g = Recorder({("POST", "services"): (200, {})})
    asyncio.run(g.create("us-east1", 1, 2))
    method, url, params, body = g.sent[0]
    assert url.endswith("/locations/us-east1/services") and params["serviceId"] == "oraculo-nodo-us-east1"
    assert body["labels"]["oraculo-demo"] == "true"
    env = {e["name"]: e["value"] for e in body["template"]["containers"][0]["env"]}
    assert env["APP_MODULE"] == "app.node:app" and env["NODO_FALLA"] == "ninguna"
    assert body["template"]["scaling"] == {"minInstanceCount": 1, "maxInstanceCount": 2}
    assert body["template"]["containers"][0]["resources"]["limits"]["cpu"] == "0.25"
    assert body["template"]["maxInstanceRequestConcurrency"] == 1


def test_plan_mode_sends_validate_only():
    g = Recorder({("POST", "services"): (200, {})}, validate_only=True)
    assert asyncio.run(g.create("us-east1", 0, 1)) == "validado por Cloud Run"
    assert g.sent[0][2]["validateOnly"] == "true"


def test_unknown_region_is_refused_before_any_call():
    g = Recorder()
    with pytest.raises(ValueError):
        asyncio.run(g.create("marte-central1", 0, 1))
    assert g.sent == []


def test_service_without_demo_label_is_invisible_and_untouchable():
    foreign = {**OWN, "labels": {}}
    g = Recorder({("GET", "oraculo-nodo-us-east1"): (200, foreign)})
    assert "us-east1" not in asyncio.run(g.list())
    with pytest.raises(RuntimeError):
        asyncio.run(g.scale("us-east1", 1, 1))
    assert all(m == "GET" for m, *_ in g.sent)


def test_state_is_read_from_the_service():
    g = Recorder({("GET", "oraculo-nodo-us-east1"): (200, OWN)})
    st = asyncio.run(g.list())["us-east1"]
    assert (st.ready, st.min_instances, st.max_instances, st.fault, st.revision) == (
        True,
        1,
        2,
        "latencia",
        "r7",
    )


def test_repair_keeps_scaling_and_clears_the_fault():
    g = Recorder(
        {("GET", "oraculo-nodo-us-east1"): (200, OWN), ("PATCH", "oraculo-nodo-us-east1"): (200, {})}
    )
    asyncio.run(g.set_fault("us-east1", None))
    method, _, _, body = g.sent[-1]
    env = {e["name"]: e["value"] for e in body["template"]["containers"][0]["env"]}
    assert method == "PATCH" and env["NODO_FALLA"] == "ninguna" and body["etag"] == "e1"
    assert body["template"]["scaling"] == {"minInstanceCount": 1, "maxInstanceCount": 2}


@pytest.mark.parametrize("fault,status", [("ninguna", 200), ("caida", 503)])
def test_node_honors_the_injected_fault(fault, status, monkeypatch):
    monkeypatch.setenv("NODO_FALLA", fault)
    assert TestClient(node_app).get("/salud").status_code == status
