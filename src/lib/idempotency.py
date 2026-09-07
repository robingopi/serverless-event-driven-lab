"""
Idempotency helper for at-least-once event delivery (SQS, EventBridge,
DynamoDB Streams all guarantee at-least-once, never exactly-once).

Uses a DynamoDB table as an idempotency store: try to PutItem with a
condition that the key doesn't already exist. If it does, this event was
already processed -> caller should skip side effects (but still succeed,
so the message doesn't retry forever).
"""
from __future__ import annotations

import os
import time
import boto3
from botocore.exceptions import ClientError


class IdempotencyStore:
    def __init__(self, table_name: str | None = None, dynamodb_resource=None):
        self.table_name = table_name or os.environ.get("IDEMPOTENCY_TABLE", "idempotency")
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(self.table_name)

    def try_claim(self, idempotency_key: str, ttl_seconds: int = 86400) -> bool:
        """
        Attempts to atomically claim this idempotency key.
        Returns True if this is the first time we've seen this key (proceed
        with side effects). Returns False if it's a duplicate (skip side
        effects, but the caller should still return success to the event
        source so it doesn't retry forever).
        """
        expires_at = int(time.time()) + ttl_seconds
        try:
            self._table.put_item(
                Item={"idempotency_key": idempotency_key, "expires_at": expires_at},
                ConditionExpression="attribute_not_exists(idempotency_key)",
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
