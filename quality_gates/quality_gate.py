#!/usr/bin/env python3
"""
Quality gate for the serverless pipeline. Aggregates:
  - unit + integration test results (JUnit XML)
  - code coverage (coverage.xml)
  - serverless-specific config checks (DLQs configured, no IAM wildcards)

Exit code 0 -> pass, pipeline continues
Exit code 1 -> fail, pipeline stops
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPORTS_DIR = Path("reports")
COVERAGE_THRESHOLD = float(os.environ.get("COVERAGE_THRESHOLD", "80"))
SERVERLESS_YML = Path("serverless.yml")


def check_junit(path: Path) -> dict:
    if not path.exists():
        return {"found": False, "passed": True, "reason": f"{path} not found, skipping"}
    tree = ET.parse(path)
    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    total = failures = errors = 0
    for suite in suites:
        total += int(suite.attrib.get("tests", 0))
        failures += int(suite.attrib.get("failures", 0))
        errors += int(suite.attrib.get("errors", 0))
    passed = failures == 0 and errors == 0 and total > 0
    return {"found": True, "passed": passed, "total": total, "failures": failures, "errors": errors}


def check_coverage(path: Path, threshold: float) -> dict:
    if not path.exists():
        return {"found": False, "passed": True, "reason": f"{path} not found, skipping"}
    tree = ET.parse(path)
    root = tree.getroot()
    line_rate = float(root.attrib.get("line-rate", 0)) * 100
    return {"found": True, "passed": line_rate >= threshold, "coverage_percent": round(line_rate, 2), "threshold": threshold}


def check_dlq_configured(path: Path) -> dict:
    """Config-lint check: every SQS-triggered / stream-triggered function
    should have a DLQ or onFailure destination defined somewhere in the file.
    This is a simple heuristic, not a full YAML-aware check, deliberately
    kept dependency-free for the lab."""
    if not path.exists():
        return {"found": False, "passed": True, "reason": f"{path} not found, skipping"}
    text = path.read_text()
    has_dlq_resource = "DLQ" in text or "deadLetterTargetArn" in text
    has_onfailure = "onFailure" in text
    passed = has_dlq_resource and has_onfailure
    return {"found": True, "passed": passed, "has_dlq_resource": has_dlq_resource, "has_onfailure_destination": has_onfailure}


def check_no_iam_wildcards(path: Path) -> dict:
    """Config-lint check: flag `Resource: "*"` or `Action: "*"` in
    iamRoleStatements blocks -- least-privilege enforcement."""
    if not path.exists():
        return {"found": False, "passed": True, "reason": f"{path} not found, skipping"}
    text = path.read_text()
    suspicious_lines = [
        line.strip() for line in text.splitlines()
        if ("Resource:" in line or "Action:" in line) and "*" in line and "GetAtt" not in line
    ]
    passed = len(suspicious_lines) == 0
    return {"found": True, "passed": passed, "suspicious_lines": suspicious_lines}


def main():
    REPORTS_DIR.mkdir(exist_ok=True)

    results = {
        "unit_tests": check_junit(REPORTS_DIR / "junit-unit.xml"),
        "integration_tests": check_junit(REPORTS_DIR / "junit-integration.xml"),
        "coverage": check_coverage(REPORTS_DIR / "coverage.xml", COVERAGE_THRESHOLD),
        "dlq_configured": check_dlq_configured(SERVERLESS_YML),
        "no_iam_wildcards": check_no_iam_wildcards(SERVERLESS_YML),
    }

    overall_pass = all(r["passed"] for r in results.values())
    summary = {"overall_result": "PASS" if overall_pass else "FAIL", "checks": results}

    with open(REPORTS_DIR / "quality-gate-result.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))

    if not overall_pass:
        print("\nQUALITY GATE FAILED - blocking pipeline promotion.", file=sys.stderr)
        sys.exit(1)

    print("\nQUALITY GATE PASSED - promoting to next stage.")
    sys.exit(0)


if __name__ == "__main__":
    main()
