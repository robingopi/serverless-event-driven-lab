import pytest

from src.handlers.process_order_stream import build_order_created_event


@pytest.mark.unit
def test_build_order_created_event_from_insert(dynamodb_stream_insert_event):
    record = dynamodb_stream_insert_event["Records"][0]
    entry = build_order_created_event(record)

    assert entry is not None
    assert entry["DetailType"] == "OrderCreated"
    assert entry["Detail"]["orderId"] == "order-abc-123"
    assert entry["Detail"]["quantity"] == 3


@pytest.mark.unit
def test_build_order_created_event_ignores_non_insert(dynamodb_stream_insert_event):
    record = dynamodb_stream_insert_event["Records"][0]
    record["eventName"] = "MODIFY"

    entry = build_order_created_event(record)

    assert entry is None
