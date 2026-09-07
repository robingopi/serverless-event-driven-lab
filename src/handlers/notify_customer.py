"""
SQS queue (fed by EventBridge rule matching "OrderCreated") -> this Lambda.

Fire-and-forget side effect: notify the customer their order was received.
Must be idempotent because SQS guarantees at-least-once delivery -- the
same message can be delivered more than once.
"""
from __future__ import annotations

import json

from src.lib.idempotency import IdempotencyStore
from src.lib.logging_utils import log_event


def send_notification(order_detail: dict) -> dict:
    """Pure-ish function representing 'send an email/SMS'. In a real system
    this would call SES/SNS/a third-party provider. Kept simple + mockable
    here so unit tests don't need real AWS calls."""
    return {
        "orderId": order_detail["orderId"],
        "customerId": order_detail["customerId"],
        "channel": "email",
        "status": "sent",
    }


def process_record(record: dict, idempotency_store: IdempotencyStore) -> dict:
    body = json.loads(record["body"])
    # EventBridge wraps the original PutEvents detail; body["detail"] is our OrderCreated payload
    detail = body.get("detail", body)
    order_id = detail["orderId"]

    if not idempotency_store.try_claim(f"notify-{order_id}"):
        log_event("duplicate notification skipped (idempotent)", orderId=order_id)
        return {"orderId": order_id, "status": "skipped_duplicate"}

    result = send_notification(detail)
    log_event("customer notified", orderId=order_id, channel=result["channel"])
    return result


def handler(event, context):
    idempotency_store = IdempotencyStore()
    results = [process_record(record, idempotency_store) for record in event.get("Records", [])]
    return {"processed": len(results), "results": results}
