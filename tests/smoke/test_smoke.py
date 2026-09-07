"""
Smoke tests - run against the REAL deployed API Gateway endpoint after
`sls deploy`. Set API_BASE_URL to the deployed httpApi URL (output by
`sls deploy` or `sls info --stage <stage>`).

Run with: pytest tests/smoke -m smoke
"""
import os
import pytest
import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:3000")


@pytest.mark.smoke
def test_create_order_returns_201():
    resp = requests.post(
        f"{API_BASE_URL}/orders",
        json={"sku": "WIDGET-001", "quantity": 1, "customerId": "smoke-test-customer"},
        timeout=10,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "orderId" in body
    assert body["status"] == "CREATED"


@pytest.mark.smoke
def test_create_order_rejects_invalid_body():
    resp = requests.post(
        f"{API_BASE_URL}/orders",
        json={"sku": "WIDGET-001"},  # missing quantity, customerId
        timeout=10,
    )
    assert resp.status_code == 400
