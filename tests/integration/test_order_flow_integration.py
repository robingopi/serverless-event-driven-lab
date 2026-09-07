"""
Integration tests using `moto` to mock AWS services in-process (DynamoDB,
EventBridge). These exercise the REAL boto3 calls in create_order.py and
process_order_stream.py against a fake-but-realistic AWS backend, without
needing real AWS credentials or a deployed stack.

Run with: pytest tests/integration -m integration
"""
import json
import os

import boto3
import pytest
from moto import mock_aws

from src.handlers.create_order import create_order
from src.handlers.process_order_stream import build_order_created_event


@pytest.fixture
def dynamodb_table():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="orders-integration-test",
            KeySchema=[{"AttributeName": "orderId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "orderId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
            StreamSpecification={"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
        )
        yield table


@pytest.fixture
def eventbridge_bus():
    with mock_aws():
        client = boto3.client("events", region_name="us-east-1")
        client.create_event_bus(Name="order-processing-bus-test")
        yield client


@pytest.mark.integration
def test_create_order_writes_real_dynamodb_item(dynamodb_table):
    order = create_order(
        {"sku": "WIDGET-001", "quantity": 5, "customerId": "cust-1"},
        dynamodb_table,
    )

    fetched = dynamodb_table.get_item(Key={"orderId": order["orderId"]})
    assert fetched["Item"]["sku"] == "WIDGET-001"
    assert fetched["Item"]["quantity"] == 5


@pytest.mark.integration
def test_eventbridge_put_events_accepts_order_created(eventbridge_bus, dynamodb_stream_insert_event):
    record = dynamodb_stream_insert_event["Records"][0]
    entry = build_order_created_event(record)
    entry["Detail"] = json.dumps(entry["Detail"])
    entry["EventBusName"] = "order-processing-bus-test"

    response = eventbridge_bus.put_events(Entries=[entry])

    assert response["FailedEntryCount"] == 0
    assert len(response["Entries"]) == 1
