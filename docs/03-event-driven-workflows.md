# Event-Driven Workflows

## The Event Flow in This Lab
```
1. POST /orders  ->  createOrder Lambda
                        - validates input
                        - writes item to DynamoDB "orders" table (status=CREATED)

2. DynamoDB Streams captures the write  ->  processOrderStream Lambda
                        - reads the INSERT record from the stream
                        - transforms it into a domain event: "OrderCreated"
                        - publishes to EventBridge custom bus

3. EventBridge rule matches detail-type "OrderCreated"
                        - Target A: SQS queue "notification-queue"
                        - Target B: starts Step Functions "OrderFulfillment" execution

4a. SQS -> notifyCustomer Lambda
                        - sends confirmation (simulated) to the customer
                        - on repeated failure, message moves to DLQ (notification-dlq)
                        - CloudWatch alarm on DLQ depth > 0 pages on-call

4b. Step Functions "OrderFulfillment" state machine
                        - ValidateOrder (Lambda)
                        - ReserveInventory (Lambda) -- Catch -> CompensateOrder
                        - ChargePayment (Lambda)    -- Catch -> ReleaseInventory (compensate)
                        - ShipOrder (Lambda)
                        - each state has Retry (transient errors) and Catch (compensating actions)
```

## Why Two Different Patterns for Steps 4a and 4b
- **Notification (4a) is a side effect that must not block or fail the main
  flow.** If sending a notification fails repeatedly, that's a problem for
  the DLQ/on-call to investigate — it should **never** roll back the order.
  SQS + a plain Lambda consumer is the right level of complexity: decoupled,
  retryable, cheap.
- **Fulfillment (4b) is a business transaction with real-money and
  real-inventory consequences that must be sequenced, retried correctly,
  and rolled back safely on partial failure.** Step Functions gives you:
  - Visual, per-execution history (which step failed, with what input)
  - Built-in `Retry` (exponential backoff) and `Catch` (route to a
    compensating state) without writing that logic in every Lambda
  - The **saga pattern**: if `ChargePayment` fails after
    `ReserveInventory` succeeded, the `Catch` transitions to
    `ReleaseInventory` to compensate, rather than leaving inventory
    silently reserved forever.

## Event Design Principles Applied
1. **Events describe facts that already happened**, named in past tense:
   `OrderCreated`, not `CreateOrder`. `CreateOrder` is a *command* (an
   instruction); `OrderCreated` is an *event* (an immutable fact). The
   `createOrder` Lambda handles the *command* over HTTP; the *event* is
   emitted afterward once the fact is durable in DynamoDB.
2. **Events carry enough data to act on, but not the entire domain model.**
   `events/order-created.json` in this repo shows the actual schema:
   order id, sku, quantity, customer id, timestamp — not the full order
   history or internal DB fields.
3. **At-least-once delivery, so consumers must be idempotent.** SQS and
   EventBridge both guarantee at-least-once, not exactly-once. Every
   consumer Lambda in this lab checks/writes an idempotency key
   (`src/lib/idempotency.py`) before acting, so a redelivered message
   doesn't double-charge a customer or double-send a notification.
4. **Dead Letter Queues everywhere a Lambda can fail.** Both the SQS
   consumer and the Lambda event-source mappings define `maximumRetryAttempts`
   plus an `OnFailure` destination/DLQ, so poison messages don't retry
   forever and don't silently vanish either — they land somewhere
   observable.
5. **Correlation ID propagation.** Every event carries an `orderId` that's
   logged (structured JSON logs) at every hop, so you can grep CloudWatch
   Logs Insights across all four Lambdas for one `orderId` and see the
   entire journey of a single order.

## Choreography Failure Mode to Watch For
With EventBridge fan-out (`OrderCreated` → multiple independent
subscribers), there's no single place that knows "did all subscribers
succeed?" If `NotifyCustomer` fails silently and there's no DLQ/alarm, you
won't know a customer never got their confirmation. This lab wires:
- A DLQ per queue
- A CloudWatch Alarm on `ApproximateNumberOfMessagesVisible` on the DLQ
This turns an invisible failure mode into a paged, actionable one.

## Testing Event-Driven Code (see also `docs/03` pairs with pytest lab's testing doc)
- **Unit tests**: call the Lambda handler function directly with a sample
  event payload (see `events/*.json` and `tests/unit/`), asserting on
  return value / side-effect calls (mocked boto3 clients).
- **Integration tests**: use `moto` (AWS service mocking library) to spin
  up an in-memory DynamoDB table + EventBridge bus + SQS queue in the test
  process, exercise the real boto3 calls end-to-end without hitting AWS.
- **Local end-to-end**: `serverless-offline` + LocalStack, described in
  `docs/05-aws-lab-guide.md`, lets you `curl` the API and watch the whole
  chain fire on your machine before ever deploying.
