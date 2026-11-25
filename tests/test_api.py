from fastapi.testclient import TestClient

from churnlab.api import app

client = TestClient(app)


def test_datasets_and_customer():
    assert client.get("/api/health").json()["status"] == "ok"
    cs = client.get("/api/customers").json()
    one = client.get(f"/api/customer/{cs[0]['id']}").json()
    assert one["id"] == cs[0]["id"]
    assert client.get("/api/customer/NOPE").status_code == 404


def test_message_and_validate_endpoints(monkeypatch):
    monkeypatch.setenv("CHURN_LLM_BACKEND", "none")
    cid = client.get("/api/customers").json()[0]["id"]
    m = client.post("/api/message", json={"customer_id": cid, "offer": "support", "lang": "en"}).json()
    assert m["checks"] == "passed"
    bad = client.post("/api/validate", json={"customer_id": cid, "offer": "support", "lang": "en",
                                             "text": m["text"] + " We guarantee 90% off forever."}).json()
    assert not bad["ok"] and "forbidden_promise" in bad["problems"]


def test_dashboard_served():
    r = client.get("/")
    assert r.status_code == 200 and "Churn" in r.text
