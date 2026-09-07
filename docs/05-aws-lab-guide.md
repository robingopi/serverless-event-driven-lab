# Hands-On Lab: Serverless & Event-Driven Order Processing on AWS

This lab deploys a real event-driven order-processing system using the
Serverless Framework, and a CodePipeline/CodeBuild CI/CD pipeline that
tests and deploys it.

## Architecture Recap
```
Client -> API Gateway -> createOrder Lambda -> DynamoDB (orders table)
                                                    |
                                            DynamoDB Streams
                                                    v
                                     processOrderStream Lambda
                                                    |
                                        publishes "OrderCreated"
                                                    v
                                            EventBridge (custom bus)
                                            /                    \
                                    SQS Queue                Step Functions
                                       |                    OrderFulfillment
                                notifyCustomer Lambda    (Validate->Reserve->
                                       |                  Charge->Ship, with
                                  (DLQ on failure)         compensation saga)
```

## Prerequisites
- AWS CLI v2 configured (`aws configure`)
- Node.js 18+ and npm (Serverless Framework is a Node CLI tool)
- Python 3.12
- Git

## Step 1 — Install Dependencies and Run Tests Locally First
```bash
cd serverless-event-driven-lab
npm install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

export PYTHONPATH=.

# Unit tests - fast, no AWS needed
pytest tests/unit -m unit -c ci/pytest.ini --cov=src --cov-config=ci/.coveragerc --cov-fail-under=80 -v

# Integration tests - moto-mocked AWS services, still no real AWS calls
pytest tests/integration -m integration -c ci/pytest.ini -v
```
You should see all unit + integration tests pass. This is exactly what the
pipeline's UnitTest and IntegrationTest stages will run.

## Step 2 — Try It Locally with serverless-offline (Optional but Recommended)
```bash
npx sls offline start
# In another terminal:
curl -X POST http://localhost:3000/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"WIDGET-001","quantity":2,"customerId":"cust-1"}'
```
Note: `serverless-offline` emulates API Gateway + Lambda but does **not**
emulate DynamoDB Streams, EventBridge, or Step Functions locally out of the
box — for full local event-chain testing, run LocalStack (see "Extensions"
below). For this lab, the offline mode is enough to sanity-check the HTTP
entrypoint before deploying.

## Step 3 — Validate the Package (Fail Fast Before Touching AWS)
```bash
npx sls package --stage dev
```
This generates the CloudFormation template AWS will actually deploy,
without deploying it — catches config typos and missing resources early.

## Step 4 — Deploy to Dev
```bash
npx sls deploy --stage dev
```
Note the `HttpApiUrl` printed in the output — this is your API Gateway
base URL, e.g. `https://abc123.execute-api.us-east-1.amazonaws.com`.

## Step 5 — Exercise the Full Event Chain
```bash
API_URL="<the HttpApiUrl from Step 4>"
curl -X POST "$API_URL/orders" \
  -H "Content-Type: application/json" \
  -d '{"sku":"WIDGET-001","quantity":2,"customerId":"cust-1"}'
```
Then check, in the AWS Console (or CLI):
- **DynamoDB** → `order-processing-system-orders-dev` table has the new item
- **CloudWatch Logs** for `processOrderStream` → shows "published OrderCreated event"
- **CloudWatch Logs** for `notifyCustomer` → shows "customer notified"
- **Step Functions** console → a new `orderFulfillment` execution ran through
  ValidateOrder → ReserveInventory → ChargePayment → ShipOrder

## Step 6 — Deploy the CI/CD Pipeline
```bash
aws cloudformation deploy \
  --template-file infra/codepipeline.yaml \
  --stack-name serverless-lab-pipeline \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides RepositoryName=serverless-event-driven-lab CoverageThreshold=80

aws cloudformation describe-stacks --stack-name serverless-lab-pipeline \
  --query "Stacks[0].Outputs"
```

## Step 7 — Push Code to Trigger the Pipeline
```bash
git init
git add .
git commit -m "Initial commit: serverless event-driven order processing lab"
git remote add origin <RepositoryCloneUrlHttp from Step 6 outputs>
git push -u origin main
```
Watch the pipeline run through: **Lint → UnitTest → Package → DeployDev →
IntegrationTest → QualityGate → ManualApprovalForProd → DeployProd →
SmokeTestProd**.

Before `DeployProd` runs, approve the manual approval action in the
CodePipeline console (or `aws codepipeline put-approval-result`).

## Step 8 — See the Saga's Compensation in Action
Force a payment failure to see the compensating action run:
```bash
# In src/handlers/order_fulfillment_tasks.py, temporarily hardcode
# charge_payment's payment_client=None branch to return False, or pass a
# test event with a very large "amount" if your payment_client mock declines
# large charges. Redeploy to dev and re-POST an order, then check the Step
# Functions execution graph: ChargePayment (red/failed) -> ReleaseInventory
# (compensating, ran automatically) -> OrderFulfillmentFailed.
```
This demonstrates the saga pattern's core value: a mid-workflow failure
doesn't leave inventory silently reserved.

## Extensions
1. **Local event-chain testing with LocalStack**: run
   `localstack start -d`, point `DYNAMODB_ENDPOINT_URL` /
   `AWS_ENDPOINT_URL` at `http://localhost:4566`, and use the
   `serverless-localstack` plugin to deploy the whole stack locally,
   including DynamoDB Streams, EventBridge, and Step Functions.
2. **Cross-account prod deploy role**: replace the broad
   `CodeBuildServiceRole` policy in `infra/codepipeline.yaml` with an
   `sts:AssumeRole` into a separate production account, requested only in
   `buildspec-deploy-prod.yml`, so dev-stage credentials can never touch
   prod resources (see `docs/04-cicd-for-serverless.md`).
3. **X-Ray tracing**: add `tracing: { lambda: true, apiGateway: true }`
   under `provider` in `serverless.yml` to get distributed traces across
   the entire event chain, one trace per `orderId`.
4. **Canary deploy verification**: after `DeployProd`, watch the
   `Canary10Percent5Minutes` CodeDeploy deployment in the console —
   traffic shifts 10% → 100% automatically unless the `ErrorsAlarm` fires,
   in which case it auto-rolls-back.

## Cleanup
```bash
npx sls remove --stage dev
npx sls remove --stage prod
aws cloudformation delete-stack --stack-name serverless-lab-pipeline
# Empty/delete the S3 artifact bucket manually if versioning retained objects
```

## Cost Note
Lambda, API Gateway (HTTP API), DynamoDB (on-demand), SQS, and EventBridge
are all pay-per-use and effectively free at this lab's traffic volume
(well within AWS free tier). Step Functions Standard workflows are billed
per state transition (a few cents for hundreds of test executions).
CodeBuild/CodePipeline costs are the same as noted in the pytest/CI-CD
lab. Remember to `sls remove` and delete the pipeline stack when finished.
