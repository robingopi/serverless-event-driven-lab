# Serverless & Event-Driven Systems — Documentation + Hands-On AWS Lab

A complete, self-contained package covering:
- Serverless architecture concepts
- Serverless Framework
- Event-driven workflows (choreography + orchestration/saga)
- CI/CD for serverless applications

...plus a working order-processing system and AWS pipeline to run it.

## Structure
```
docs/
  01-serverless-architecture-concepts.md
  02-serverless-framework.md
  03-event-driven-workflows.md
  04-cicd-for-serverless.md
  05-aws-lab-guide.md            <- STEP-BY-STEP: deploy & run on AWS

serverless.yml                    <- Serverless Framework IaC: all functions + events + resources
statemachine/order_fulfillment.asl.json  <- Step Functions saga definition

src/handlers/
  create_order.py                 <- POST /orders -> DynamoDB
  process_order_stream.py         <- DynamoDB Streams -> EventBridge "OrderCreated"
  notify_customer.py               <- SQS -> idempotent customer notification
  order_fulfillment_tasks.py       <- Step Functions saga steps (validate/reserve/charge/ship/compensate)
src/lib/
  idempotency.py, logging_utils.py

events/                           <- sample event payloads (API GW, DynamoDB Stream, EventBridge, SQS)

tests/
  unit/                           <- fast, mocked (pytest -m unit)
  integration/                    <- moto-backed real boto3 calls (pytest -m integration)
  smoke/                          <- against real deployed API (pytest -m smoke)

quality_gates/quality_gate.py     <- aggregates tests + coverage + serverless config checks (DLQs, IAM least-privilege)

ci/
  buildspec-lint.yml, buildspec-unit.yml, buildspec-package.yml,
  buildspec-deploy-dev.yml, buildspec-integration.yml,
  buildspec-quality-gate.yml, buildspec-deploy-prod.yml, buildspec-smoke.yml

infra/codepipeline.yaml            <- CloudFormation: CodeCommit + 8 CodeBuild projects + CodePipeline
```

## Quickest Path to Running This
1. Read `docs/01` through `docs/04` for the concepts (20–25 min read).
2. Follow `docs/05-aws-lab-guide.md` to deploy the app and the pipeline to
   your AWS account, exercise the full event chain, and watch the saga's
   compensation logic run when payment fails.

## Local Quick Test (no AWS needed)
```bash
npm install
pip install -r requirements.txt -r requirements-dev.txt
export PYTHONPATH=.
pytest tests/unit -m unit -c ci/pytest.ini --cov=src --cov-config=ci/.coveragerc --cov-fail-under=80 -v
pytest tests/integration -m integration -c ci/pytest.ini -v
```

## Pipeline Flow Implemented
```
Source (CodeCommit)
  -> Lint (flake8)
  -> UnitTest (pytest -m unit, coverage >= 80%)
  -> Package (sls package --stage dev, validates CloudFormation before deploying)
  -> DeployDev (sls deploy --stage dev)
  -> IntegrationTest (pytest -m integration, moto-mocked AWS)
  -> QualityGate (tests + coverage + DLQ/IAM config checks -> pass/fail)
  -> ManualApprovalForProd
  -> DeployProd (sls deploy --stage prod, canary 10%->100% via CodeDeploy)
  -> SmokeTestProd (pytest -m smoke against real prod API Gateway URL)
```
