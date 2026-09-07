import pytest

from src.handlers.notify_customer import process_record, send_notification


@pytest.mark.unit
def test_send_notification():
    detail = {"orderId": "order-1", "customerId": "cust-1"}
    result = send_notification(detail)
    assert result["status"] == "sent"
    assert result["orderId"] == "order-1"


@pytest.mark.unit
def test_process_record_sends_notification_first_time(sqs_order_created_event, fake_idempotency_store):
    record = sqs_order_created_event["Records"][0]
    result = process_record(record, fake_idempotency_store)
    assert result["status"] == "sent"


@pytest.mark.unit
def test_process_record_skips_duplicate(sqs_order_created_event, fake_idempotency_store):
    record = sqs_order_created_event["Records"][0]
    process_record(record, fake_idempotency_store)  # first delivery
    result = process_record(record, fake_idempotency_store)  # redelivered (at-least-once)

    assert result["status"] == "skipped_duplicate"
