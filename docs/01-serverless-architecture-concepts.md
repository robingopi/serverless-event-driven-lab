# Serverless Architecture Concepts

## What "Serverless" Actually Means
Servers still exist — you just don't manage them. The cloud provider handles
provisioning, patching, scaling, and availability. You deploy *code* (a
function, a container) or *configuration* (an API Gateway route, an
EventBridge rule) and pay only for what executes.

Two distinct but related ideas:
1. **FaaS (Functions-as-a-Service)** — AWS Lambda, Azure Functions, GCP
   Cloud Functions. Short-lived, stateless, event-triggered compute.
2. **Managed/serverless services** — DynamoDB, S3, EventBridge, SQS, SNS,
   Step Functions, Aurora Serverless, API Gateway. No servers to size,
   scale automatically, pay-per-use or pay-per-request.

A "serverless architecture" composes these building blocks instead of
running a monolith on EC2/ECS.

## Core Characteristics
| Characteristic | Implication |
|---|---|
| No server management | No OS patching, no capacity planning |
| Automatic scaling | Scales to zero and to thousands of concurrent executions |
| Pay-per-use | Billed per invocation/duration/request, not per idle hour |
| Event-driven by nature | Functions are triggered by events (HTTP request, queue message, stream record, schedule) |
| Stateless execution | State must live externally (DynamoDB, S3, Step Functions) — never assume the same container instance handles the next invocation |
| Short execution limits | AWS Lambda max timeout is 15 minutes — long-running work needs Step Functions or async patterns |

## Building Blocks Used in This Lab
- **AWS Lambda** — the compute unit. One handler per responsibility
  (single-purpose functions, not a monolith bundled into one Lambda).
- **Amazon API Gateway** — HTTP entry point, routes requests to Lambda.
- **Amazon DynamoDB + DynamoDB Streams** — the datastore *and* a native
  change-data-capture event source (every write emits a stream record).
- **Amazon EventBridge** — the central event bus for domain events
  (`OrderCreated`, `OrderShipped`, etc.), enabling **choreography**.
- **Amazon SQS** — durable buffering/decoupling between producer and
  consumer, with a **Dead Letter Queue (DLQ)** for poison messages.
- **AWS Step Functions** — **orchestration** for a multi-step workflow
  (order fulfillment saga) where you need visibility, retries, and
  explicit sequencing instead of implicit choreography.

## Choreography vs Orchestration (Core Design Decision)
- **Choreography**: each service reacts to events independently; no central
  controller. Example: `OrderCreated` event on EventBridge triggers
  `InventoryService`, `NotificationService`, and `AnalyticsService`
  independently, each subscribed to the same event. Loosely coupled, but
  harder to see "the whole flow" and to handle cross-step failure/rollback.
- **Orchestration**: a central workflow (Step Functions state machine)
  explicitly calls each step in order, handles retries/catch/rollback
  (saga pattern), and gives you a visual execution history per order.
  Tighter coupling to the orchestrator, but far easier to reason about
  and debug for critical multi-step business transactions.

This lab implements **both**, to show when each fits:
- Choreography: `OrderCreated` → EventBridge → SQS → `NotifyCustomer` Lambda
  (fire-and-forget side effect, doesn't need to block order creation)
- Orchestration: `OrderFulfillmentStateMachine` (Step Functions) explicitly
  sequences ValidateOrder → ReserveInventory → ChargePayment → ShipOrder,
  with compensating actions on failure (saga pattern)

## Serverless Trade-offs (Being Honest About Both Sides)
**Pros**
- No idle cost; scales automatically; less operational burden
- Fine-grained scaling per function
- Fast to iterate — deploy a single function without redeploying everything

**Cons / things to design around**
- **Cold starts** — first invocation after idle has extra latency
  (mitigated with provisioned concurrency, smaller deployment packages,
  or keeping runtimes like Node/Python which start faster than JVM-based ones)
- **Distributed system complexity** — what was one process is now many
  functions communicating over events; requires distributed tracing
  (AWS X-Ray), correlation IDs, and careful idempotency design
- **Vendor lock-in** — heavy use of proprietary services (EventBridge,
  Step Functions) trades portability for productivity
- **Testing complexity** — you can't just run "the app" locally the same
  way; local emulation (LocalStack, SAM local, `serverless-offline`) and
  strong unit test isolation become essential (see `03-event-driven-workflows.md`
  and the AWS lab guide)
- **Debugging distributed event chains** — a bug three hops downstream in
  an event chain is harder to trace than a stack trace in a monolith

## Where This Fits in the Bigger Picture
This lab builds a small **Order Processing** system:
```
Client -> API Gateway -> CreateOrder Lambda -> DynamoDB (orders table)
                                                    |
                                            DynamoDB Streams
                                                    v
                                     OrderStreamProcessor Lambda
                                                    |
                                        publishes "OrderCreated"
                                                    v
                                            EventBridge (custom bus)
                                            /                    \
                                    SQS Queue                Step Functions
                                       |                    OrderFulfillment
                                NotifyCustomer Lambda        state machine
```
See `docs/03-event-driven-workflows.md` for the full event flow and
`docs/05-aws-lab-guide.md` to deploy and run it.
