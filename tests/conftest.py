import json
import os

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import pytest


@pytest.fixture
def sample_order_body():
    return {"sku": "WIDGET-001", "quantity": 3, "customerId": "cust-123"}


@pytest.fixture
def api_gateway_event(sample_order_body):
    with open("events/api-gateway-create-order.json") as f:
        event = json.load(f)
    event["body"] = json.dumps(sample_order_body)
    return event


@pytest.fixture
def dynamodb_stream_insert_event():
    with open("events/dynamodb-stream-insert.json") as f:
        return json.load(f)


@pytest.fixture
def sqs_order_created_event():
    with open("events/sqs-order-created.json") as f:
        return json.load(f)


class FakeOrdersTable:
    """In-memory fake for the unit tests - avoids mocking boto3 internals."""

    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[Item["orderId"]] = Item
        return {}

    def get_item(self, Key):
        item = self.items.get(Key["orderId"])
        return {"Item": item} if item else {}


@pytest.fixture
def fake_orders_table():
    return FakeOrdersTable()


class FakeIdempotencyStore:
    """In-memory fake for IdempotencyStore, avoids requiring real DynamoDB in unit tests."""

    def __init__(self):
        self._claimed = set()

    def try_claim(self, idempotency_key: str, ttl_seconds: int = 86400) -> bool:
        if idempotency_key in self._claimed:
            return False
        self._claimed.add(idempotency_key)
        return True


@pytest.fixture
def fake_idempotency_store():
    return FakeIdempotencyStore()


class FakeInventoryClient:
    def __init__(self, available_qty=100):
        self.available_qty = available_qty
        self.reserved = {}

    def get_available(self, sku):
        return self.available_qty

    def reserve(self, sku, qty):
        self.reserved[sku] = self.reserved.get(sku, 0) + qty

    def release(self, sku, qty):
        self.reserved[sku] = self.reserved.get(sku, 0) - qty


class FakePaymentClient:
    def __init__(self, should_approve=True):
        self.should_approve = should_approve
        self.charges = []

    def charge(self, customer_id, amount):
        self.charges.append((customer_id, amount))
        return self.should_approve


class FakeShippingClient:
    def create_shipment(self, order_id):
        return f"TRACK-{order_id}"


@pytest.fixture
def fake_inventory_client():
    return FakeInventoryClient()


@pytest.fixture
def fake_payment_client():
    return FakePaymentClient()


@pytest.fixture
def fake_shipping_client():
    return FakeShippingClient()
