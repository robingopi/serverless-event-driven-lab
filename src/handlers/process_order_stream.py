"""
DynamoDB Stream (orders table) -> this Lambda -> EventBridge custom bus.

Translates a raw DynamoDB "INSERT" stream record into a clean domain event
("OrderCreated") that downstream consumers (SQS notifier, Step Functions
fulfillment workflow) subscribe to via EventBridge rules. This is the
boundary between "storage implementation detail" (DynamoDB record shape)
and "public domain event contract" (see events/order-created.json).
"""
from __future__ import annotations

import os
import boto3

from src.lib.logging_utils import log_event

EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "order-processing-bus")
_eventbridge = boto3.client("events")


def _deserialize_dynamodb_image(image: dict) -> dict:
    """Minimal DynamoDB JSON -> plain dict deserializer for the attribute
    types this table actually uses (S, N)."""
    result = {}
    for key, typed_value in image.items():
        if "S" in typed_value:
            result[key] = typed_value["S"]
        elif "N" in typed_value:
            result[key] = int(typed_value["N"]) if "." not in typed_value["N"] else float(typed_value["N"])
        else:
            result[key] = typed_value
    return result


def build_order_created_event(record: dict) -> dict | None:
    """Pure transformation: stream record -> EventBridge PutEvents entry (or
    None if this record doesn't represent a new order, e.g. it's a MODIFY)."""
    if record.get("eventName") != "INSERT":
        return None

    new_image = record["dynamodb"]["NewImage"]
    order = _deserialize_dynamodb_image(new_image)

    return {
        "Source": "order-processing.orders",
        "DetailType": "OrderCreated",
        "Detail": {
            "orderId": order["orderId"],
            "sku": order["sku"],
            "quantity": order["quantity"],
            "customerId": order["customerId"],
            "createdAt": order["createdAt"],
        },
    }


def handler(event, context):
    import json

    entries = []
    for record in event.get("Records", []):
        entry = build_order_created_event(record)
        if entry:
            entries.append({**entry, "Detail": json.dumps(entry["Detail"]), "EventBusName": EVENT_BUS_NAME})

    if not entries:
        return {"published": 0}

    response = _eventbridge.put_events(Entries=entries)
    for entry, result in zip(entries, response.get("Entries", [])):
        detail = json.loads(entry["Detail"])
        log_event("published OrderCreated event", orderId=detail["orderId"], eventId=result.get("EventId"))

    return {"published": len(entries)}
