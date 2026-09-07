"""
POST /orders

API Gateway (HTTP API) -> this Lambda -> DynamoDB "orders" table.

This handler ONLY validates input and durably persists the order. It does
NOT publish any event itself -- that's the job of process_order_stream.py,
triggered by the DynamoDB Stream. This separation means the "order exists"
fact and "notify downstream systems" fact can never disagree: if the write
succeeds, the stream *will* fire, guaranteed by DynamoDB itself.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import boto3

ORDERS_TABLE = os.environ.get("ORDERS_TABLE", "orders")
_dynamodb = boto3.resource("dynamodb")


class ValidationError(Exception):
    pass


def _validate(body: dict) -> dict:
    required = ["sku", "quantity", "customerId"]
    missing = [f for f in required if f not in body]
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(missing)}")
    if not isinstance(body["quantity"], int) or body["quantity"] <= 0:
        raise ValidationError("quantity must be a positive integer")
    return body


def create_order(body: dict, table) -> dict:
    """Pure-ish business logic, separated from the Lambda event/response
    plumbing below so it's trivially unit-testable with a fake table."""
    validated = _validate(body)
    order_id = str(uuid.uuid4())
    item = {
        "orderId": order_id,
        "sku": validated["sku"],
        "quantity": validated["quantity"],
        "customerId": validated["customerId"],
        "status": "CREATED",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    table.put_item(Item=item)
    return item


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        table = _dynamodb.Table(ORDERS_TABLE)
        order = create_order(body, table)
        return {
            "statusCode": 201,
            "body": json.dumps(order),
        }
    except ValidationError as e:
        return {"statusCode": 400, "body": json.dumps({"error": str(e)})}
    except Exception as e:  # noqa: BLE001 - top-level Lambda handler boundary
        return {"statusCode": 500, "body": json.dumps({"error": "internal_error", "detail": str(e)})}
