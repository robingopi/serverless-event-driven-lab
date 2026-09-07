import pytest

from src.handlers.order_fulfillment_tasks import (
    validate_order,
    reserve_inventory,
    charge_payment,
    ship_order,
    release_inventory,
    InsufficientInventoryError,
    PaymentDeclinedError,
)


@pytest.fixture
def order_event():
    return {"orderId": "order-1", "sku": "WIDGET-001", "quantity": 3, "customerId": "cust-1"}


@pytest.mark.unit
def test_validate_order_success(order_event):
    result = validate_order(order_event)
    assert result["validated"] is True


@pytest.mark.unit
def test_validate_order_missing_field_raises():
    with pytest.raises(ValueError):
        validate_order({"orderId": "o1"})


@pytest.mark.unit
def test_reserve_inventory_success(order_event, fake_inventory_client):
    result = reserve_inventory(order_event, inventory_client=fake_inventory_client)
    assert result["inventoryReserved"] is True
    assert fake_inventory_client.reserved["WIDGET-001"] == 3


@pytest.mark.unit
def test_reserve_inventory_insufficient_raises(order_event, fake_inventory_client):
    fake_inventory_client.available_qty = 1
    with pytest.raises(InsufficientInventoryError):
        reserve_inventory(order_event, inventory_client=fake_inventory_client)


@pytest.mark.unit
def test_charge_payment_success(order_event, fake_payment_client):
    result = charge_payment(order_event, payment_client=fake_payment_client)
    assert result["paymentCharged"] is True
    assert len(fake_payment_client.charges) == 1


@pytest.mark.unit
def test_charge_payment_declined_raises(order_event, fake_payment_client):
    fake_payment_client.should_approve = False
    with pytest.raises(PaymentDeclinedError):
        charge_payment(order_event, payment_client=fake_payment_client)


@pytest.mark.unit
def test_ship_order_success(order_event, fake_shipping_client):
    result = ship_order(order_event, shipping_client=fake_shipping_client)
    assert result["shipped"] is True
    assert result["trackingNumber"] == "TRACK-order-1"


@pytest.mark.unit
def test_release_inventory_compensates_reservation(order_event, fake_inventory_client):
    reserved = reserve_inventory(order_event, inventory_client=fake_inventory_client)
    assert fake_inventory_client.reserved["WIDGET-001"] == 3

    compensated = release_inventory(reserved, inventory_client=fake_inventory_client)

    assert compensated["compensated"] is True
    assert fake_inventory_client.reserved["WIDGET-001"] == 0


@pytest.mark.unit
def test_full_saga_happy_path(order_event, fake_inventory_client, fake_payment_client, fake_shipping_client):
    """Runs the whole saga in-process the way Step Functions would, but
    without needing a deployed state machine -- fast feedback for developers."""
    state = validate_order(order_event)
    state = reserve_inventory(state, inventory_client=fake_inventory_client)
    state = charge_payment(state, payment_client=fake_payment_client)
    state = ship_order(state, shipping_client=fake_shipping_client)

    assert state["shipped"] is True
    assert state["paymentCharged"] is True
    assert state["inventoryReserved"] is True


@pytest.mark.unit
def test_full_saga_compensates_on_payment_failure(order_event, fake_inventory_client, fake_payment_client):
    fake_payment_client.should_approve = False

    state = validate_order(order_event)
    state = reserve_inventory(state, inventory_client=fake_inventory_client)
    assert fake_inventory_client.reserved["WIDGET-001"] == 3

    with pytest.raises(PaymentDeclinedError):
        charge_payment(state, payment_client=fake_payment_client)

    # This is what the state machine's Catch -> ReleaseInventory does automatically
    compensated = release_inventory(state, inventory_client=fake_inventory_client)
    assert fake_inventory_client.reserved["WIDGET-001"] == 0
    assert compensated["compensated"] is True
