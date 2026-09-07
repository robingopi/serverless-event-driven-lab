# Serverless Framework

## What It Is
The Serverless Framework is an open-source CLI/IaC tool that lets you define
Lambda functions, their triggers, and the AWS resources they need in one
declarative YAML file (`serverless.yml`), then deploy the whole stack with a
single command. Under the hood, on AWS, it generates and deploys a
**CloudFormation** template — so you get all of CloudFormation's
reliability (atomic deploys, rollback on failure, drift detection) without
hand-writing hundreds of lines of template.

## Why Use It (vs raw CloudFormation/CDK/Terraform)
| Tool | Best for |
|---|---|
| Serverless Framework | Fastest way to wire Lambda + triggers (HTTP, SQS, streams, schedule, EventBridge) with minimal boilerplate; huge plugin ecosystem |
| AWS SAM | Similar goal, AWS-native, tighter local-testing integration (`sam local`) |
| AWS CDK | Full programming language (TypeScript/Python) for complex custom infra logic |
| Terraform | Multi-cloud, mature state management, common in already-Terraform shops |

This lab uses Serverless Framework because event-source wiring (DynamoDB
Streams, SQS, EventBridge rules, scheduled events) is expressed in a few
lines of YAML instead of full IAM policies + CFN resources by hand.

## Anatomy of `serverless.yml` (this lab's file, annotated)
```yaml
service: order-processing-system

provider:
  name: aws
  runtime: python3.12
  stage: ${opt:stage, 'dev'}       # sls deploy --stage prod
  region: us-east-1
  environment:
    ORDERS_TABLE: ${self:service}-orders-${self:provider.stage}
    EVENT_BUS_NAME: ${self:service}-bus-${self:provider.stage}
  iam:
    role:
      statements:                  # least-privilege IAM per function is
        - Effect: Allow            # defined at the function level below;
          Action: [...]            # this provider-level block covers shared needs

functions:
  createOrder:
    handler: src/handlers/create_order.handler
    events:
      - httpApi:
          path: /orders
          method: post

  processOrderStream:
    handler: src/handlers/process_order_stream.handler
    events:
      - stream:
          type: dynamodb
          arn: !GetAtt OrdersTable.StreamArn
          startingPosition: LATEST
          batchSize: 10
          maximumRetryAttempts: 3

  notifyCustomer:
    handler: src/handlers/notify_customer.handler
    events:
      - sqs:
          arn: !GetAtt NotificationQueue.Arn
          batchSize: 5

resources:
  Resources:
    OrdersTable: ...       # DynamoDB table with StreamSpecification enabled
    NotificationQueue: ... # SQS queue + redrive policy pointing at a DLQ
    NotificationDLQ: ...
    EventBus: ...          # custom EventBridge bus
```
Full working file: `serverless.yml` in the project root.

## Key Serverless Framework Concepts Used

### 1. Functions and Events
Each `functions.<name>.events` entry wires an **event source** to a
Lambda **without you writing the IAM policy or the event-source-mapping
resource by hand** — the framework generates it.

### 2. Stages
`stage: ${opt:stage, 'dev'}` means `serverless deploy --stage dev` and
`serverless deploy --stage prod` create **fully separate stacks** (separate
DynamoDB tables, separate API Gateway, separate everything) — this is how
you get isolated dev/staging/prod environments without manual duplication.

### 3. `resources` block (raw CloudFormation)
Anything the framework's shorthand doesn't cover (e.g., a DynamoDB table
with specific stream settings, a custom EventBridge bus, an SQS DLQ with a
redrive policy) is defined as raw CloudFormation directly inside
`resources.Resources` — Serverless Framework merges this into the generated
template.

### 4. IAM Least Privilege Per Function
```yaml
functions:
  createOrder:
    handler: src/handlers/create_order.handler
    iamRoleStatements:
      - Effect: Allow
        Action: dynamodb:PutItem
        Resource: !GetAtt OrdersTable.Arn
```
Each function gets *only* the permissions it needs — `createOrder` can
`PutItem` but not `Scan` the whole table, for example.

### 5. Plugins Used
- `serverless-python-requirements` — bundles `pip` dependencies into the
  deployment package automatically
- `serverless-offline` — emulates API Gateway + Lambda locally for fast
  iteration without deploying

## Local Development Workflow
```bash
npm install                       # installs serverless framework + plugins
sls offline start                 # emulate API Gateway + Lambda locally
curl -X POST http://localhost:3000/orders -d '{"sku":"abc","qty":2}'
```

## Deploying
```bash
sls deploy --stage dev            # deploy/update entire stack to dev
sls deploy function -f createOrder --stage dev   # fast update of just one function's code
sls remove --stage dev            # tear down the entire stack
```

## Why This Matters for CI/CD
Because `serverless deploy` is one deterministic command driven entirely by
`serverless.yml` + code, it plugs cleanly into a CI/CD pipeline: the same
command that a developer runs locally is exactly what CodeBuild runs in
the pipeline — no drift between "how I deployed it on my machine" and
"how the pipeline deploys it." See `docs/04-cicd-for-serverless.md`.
