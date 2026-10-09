"""API conventions: REQ-API-01, REQ-API-02. Test case IDs match docs/03-test-cases.csv."""

from conftest import error_code


def test_TC_API_001_health_reports_status_and_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert isinstance(r.json()["version"], str) and r.json()["version"]


def test_TC_API_002_business_error_uses_standard_body(client):
    r = client.get("/sellers/S99999")
    assert r.status_code == 404
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "SELLER_NOT_FOUND"
    assert body["error"]["message"]
    assert isinstance(body["error"]["details"], list)


def test_TC_API_003_missing_field_reports_validation_error_location(client):
    r = client.post("/sellers", json={"seller_id": "S00001", "store_id": "T1000"})
    assert r.status_code == 422
    assert error_code(r) == "VALIDATION_ERROR"
    assert any(d["loc"][-1] == "name" for d in r.json()["error"]["details"])


def test_TC_API_004_unknown_body_field_is_rejected(client):
    r = client.post("/sellers", json={"seller_id": "S00001", "name": "Ana", "store_id": "T1000",
                                      "bonus": 1000})
    assert r.status_code == 422
    assert error_code(r) == "VALIDATION_ERROR"


def test_TC_API_005_money_is_a_two_decimal_string(api):
    api.seller("S00001")
    r = api.sale("2026-10-15", 1500.5, [("S00001", 100)])
    tid = r.json()["transaction_id"]
    body = api.c.get(f"/transactions/{tid}").json()
    assert body["amount"] == "1500.50"
    assert body["credits"][0]["credit"] == "1500.50"


def test_TC_API_006_unknown_route_and_method_use_standard_body(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert "error" in r.json() and r.json()["error"]["code"]
    r = client.delete("/health")
    assert r.status_code == 405
    assert "error" in r.json() and r.json()["error"]["code"]


def test_TC_API_007_malformed_json_is_a_validation_error(client):
    r = client.post("/sellers", content=b"{", headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert error_code(r) == "VALIDATION_ERROR"
