# CI/CD for Serverless Applications

## Why Serverless CI/CD Is Different
- There's no "server" to SSH into or container to build in the traditional
  sense — the "deploy" step is `serverless deploy`, which itself creates/
  updates a CloudFormation stack.
- Deployment is naturally **per-stage** (dev/staging/prod are separate
  stacks), so promotion between environments means running the same deploy
  command with a different `--stage` flag against a different AWS account
  or role — not copying artifacts between servers.
- Because functions are small and independent, CI can (and should) run
  **fast unit tests against handler code with mocked AWS clients** before
  ever touching real infrastructure, then a **narrower set of integration
  tests against the actually-deployed dev stack** after deploy.

## Pipeline Stages Implemented in This Lab
```
Source (CodeCommit)
  -> Lint          (flake8 on src/)
  -> UnitTest       (pytest -m unit, handlers tested with mocked boto3)
  -> Package        (sls package --stage dev  -- validates serverless.yml + builds artifact, no deploy yet)
  -> DeployDev       (sls deploy --stage dev)
  -> IntegrationTest (pytest -m integration, moto-backed AND/OR hits the real deployed dev API + EventBridge)
  -> QualityGate     (aggregates unit/integration/coverage -> pass/fail, same pattern as pytest lab)
  -> ManualApproval  (human approves prod release)
  -> DeployProd      (sls deploy --stage prod)
  -> SmokeTestProd   (pytest -m smoke against the real prod API Gateway URL)
```

## Why `Package` Is Its Own Stage Before `DeployDev`
`sls package` builds the CloudFormation template + zips the code **without**
deploying it. Running this as a separate stage catches:
- YAML/config errors
- Missing IAM permissions the framework can detect
- Dependency packaging failures
...all *before* you touch a real AWS environment, keeping the "fail fast /
shift-left" principle from the pytest & CI/CD pipeline lab.

## Handling Multi-Account / Multi-Stage Deploys Safely
Best practice (and what `infra/codepipeline.yaml` sets up) is:
- **`dev` stage** deploys using the CodeBuild project's own IAM role in a
  shared dev/sandbox account.
- **`prod` stage** deploy stage **assumes a separate cross-account IAM role**
  scoped to the production account, requested only after `ManualApproval`
  passes. This means a bug in the dev pipeline can never accidentally
  touch production resources — the credentials simply aren't available
  until a human approves.
- Secrets (API keys, DB creds) are never hardcoded in `serverless.yml` —
  they're pulled at deploy/runtime from **AWS Systems Manager Parameter
  Store** or **Secrets Manager** using `${ssm:/path/to/param}` syntax in
  `serverless.yml`, and CodeBuild's role is granted read-only access to
  just those parameter paths.

## Rollback Strategy
`serverless deploy` is backed by CloudFormation, which **automatically
rolls back the entire stack** if any resource fails to update — you don't
get a half-updated stack. For an additional safety net at the Lambda
level, this lab's `provider.deploymentSettings` (see `serverless.yml`)
enables **CodeDeploy-based canary deployment for Lambda aliases**:
- 10% of traffic shifts to the new function version
- CloudWatch Alarms (error rate, latency) are monitored for N minutes
- If healthy, traffic shifts to 100%; if alarms fire, CodeDeploy
  automatically rolls back to the previous version — zero manual
  intervention needed.

## Quality Gate for Serverless (same concept, serverless-specific checks)
In addition to the generic checks from the pytest/CI-CD lab (test pass
rate, coverage %, security scan), a serverless-specific quality gate adds:
- **`sls package` succeeded** (i.e., the CloudFormation template is valid)
- **No IAM `*` wildcard resources** in generated policies (a simple grep/
  check against the packaged CloudFormation template, enforcing least
  privilege)
- **DLQs configured** on every async event source (SQS/EventBridge/Stream
  Lambda triggers) — a config-linting check, not a test, but still a gate

See `quality_gates/quality_gate.py` — extended from the pytest lab's
version with a `check_iam_wildcards()` and `check_dlq_configured()` step.

## Local Command Reference (mirrors what CI runs)
```bash
# What CI runs at each stage — run these yourself locally first (shift-left)
flake8 src
pytest tests/unit -m unit --cov=src --cov-fail-under=80
sls package --stage dev
sls deploy --stage dev
pytest tests/integration -m integration
python quality_gates/quality_gate.py
sls deploy --stage prod   # only after manual approval in the real pipeline
pytest tests/smoke -m smoke
```

Full working buildspecs: `ci/buildspec-*.yml`. Full pipeline infrastructure:
`infra/codepipeline.yaml`. Step-by-step walkthrough: `docs/05-aws-lab-guide.md`.
