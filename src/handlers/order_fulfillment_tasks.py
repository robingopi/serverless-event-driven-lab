"""
Individual Step Functions task handlers for the OrderFulfillment saga
(statemachine/order_fulfillment.asl.json). Each function is invoked as a
single Lambda task state. Compensating actions (ReleaseInventory) are
invoked by the state machine's Catch block on downstream failure, not by
this code directly -- keeping the saga's control flow visible in the ASL
definition rather than hidden in application code.
"""
from __future__ import annotations


class InsufficientInventoryError(Exception):
    pass


class PaymentDeclinedError(Exception):
    pass


def validate_order(event: dict, context=None) -> dict:
    """ValidateOrder state. Raises if the order is structurally invalid."""
    required = ["orderId", "sku", "quantity", "customerId"]
    missing = [f for f in required if f not in event]
    if missing:
        raise ValueError(f"Invalid order, missing: {missing}")
    return {**event, "validated": True}


def reserve_inventory(event: dict, context=None, inventory_client=None) -> dict:
    """ReserveInventory state. inventory_client is injectable for tests."""
    available = inventory_client.get_available(event["sku"]) if inventory_client else 100
    if available < event["quantity"]:
        raise InsufficientInventoryError(f"Only {available} of {event['sku']} available")
    if inventory_client:
        inventory_client.reserve(event["sku"], event["quantity"])
    return {**event, "inventoryReserved": True}


def charge_payment(event: dict, context=None, payment_client=None) -> dict:
    """ChargePayment state. Raises PaymentDeclinedError on failure, which
    the state machine catches and routes to ReleaseInventory (compensation)."""
    amount = event.get("amount", event["quantity"] * event.get("unitPrice", 10.0))
    approved = payment_client.charge(event["customerId"], amount) if payment_client else True
    if not approved:
        raise PaymentDeclinedError(f"Payment declined for customer {event['customerId']}")
    return {**event, "paymentCharged": True, "amountCharged": amount}


def ship_order(event: dict, context=None, shipping_client=None) -> dict:
    """ShipOrder state - final happy-path step."""
    tracking_number = shipping_client.create_shipment(event["orderId"]) if shipping_client else "TRACK-SIMULATED"
    return {**event, "shipped": True, "trackingNumber": tracking_number}


def release_inventory(event: dict, context=None, inventory_client=None) -> dict:
    """Compensating action - runs only if a later step (ChargePayment)
    failed after inventory was already reserved. This is the 'undo' half
    of the saga pattern."""
    if inventory_client and event.get("inventoryReserved"):
        inventory_client.release(event["sku"], event["quantity"])
    return {**event, "inventoryReserved": False, "compensated": True}
