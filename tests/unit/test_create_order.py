import json
import pytest

from src.handlers.create_order import create_order, handler, ValidationError


@pytest.mark.unit
def test_create_order_success(sample_order_body, fake_orders_table):
    order = create_order(sample_order_body, fake_orders_table)
    assert order["sku"] == "WIDGET-001"
    assert order["status"] == "CREATED"
    assert order["orderId"] in fake_orders_table.items


@pytest.mark.unit
def test_create_order_missing_field_raises(fake_orders_table):
    with pytest.raises(ValidationError, match="Missing required fields"):
        create_order({"sku": "WIDGET-001"}, fake_orders_table)


@pytest.mark.unit
def test_create_order_invalid_quantity_raises(fake_orders_table):
    with pytest.raises(ValidationError, match="quantity must be a positive integer"):
        create_order({"sku": "W", "quantity": -1, "customerId": "c"}, fake_orders_table)


@pytest.mark.unit
def test_handler_returns_201_on_success(api_gateway_event, monkeypatch, fake_orders_table):
    import src.handlers.create_order as mod
    monkeypatch.setattr(mod, "_dynamodb", type("R", (), {"Table": lambda self, name: fake_orders_table})())

    response = mod.handler(api_gateway_event, None)

    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert body["sku"] == "WIDGET-001"


@pytest.mark.unit
def test_handler_returns_400_on_invalid_body(monkeypatch, fake_orders_table):
    import src.handlers.create_order as mod
    monkeypatch.setattr(mod, "_dynamodb", type("R", (), {"Table": lambda self, name: fake_orders_table})())

    event = {"body": json.dumps({"sku": "only-sku"})}
    response = mod.handler(event, None)

    assert response["statusCode"] == 400
