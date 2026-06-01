"""
WS-5: Declarative data quality checks.
Each rule has an explicit BREAK or ALERT policy and a remediation runbook reference.
Rules are config — not buried in pipeline code.
"""

import json
import logging
import re
import statistics
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Policy(Enum):
    BREAK = "BREAK"    # pipeline halts, incident raised
    ALERT = "ALERT"    # pipeline continues, Slack notification


@dataclass
class QualityRule:
    rule_id: str
    description: str
    policy: Policy
    check_fn: Callable[[list[dict]], list[str]]  # returns list of violation messages
    remediation_runbook: str   # link or reference to runbook


@dataclass
class QualityResult:
    rule_id: str
    policy: Policy
    passed: bool
    violations: list[str]


# ── Null rate check ───────────────────────────────────────────────────────────

def make_null_rate_check(
    field: str,
    threshold: float,
    policy: Policy,
    key_column: bool = True,
) -> QualityRule:
    def check(records: list[dict]) -> list[str]:
        if not records:
            return []
        null_count = sum(1 for r in records if not r.get(field))
        null_rate = null_count / len(records)
        if null_rate > threshold:
            return [f"Null rate for '{field}' is {null_rate:.1%} (threshold {threshold:.1%})"]
        return []

    col_type = "key" if key_column else "nullable"
    return QualityRule(
        rule_id=f"null_rate_{field}",
        description=f"Null rate for {col_type} column '{field}' must be ≤ {threshold:.0%}",
        policy=policy,
        check_fn=check,
        remediation_runbook="docs/runbooks/null_explosion.md",
    )


# ── Schema drift check ────────────────────────────────────────────────────────

def make_schema_drift_check(expected_columns: set[str]) -> QualityRule:
    def check(records: list[dict]) -> list[str]:
        if not records:
            return []
        actual = set(records[0].keys()) - {"source_system", "run_id", "ingested_at", "row_count", "schema_fingerprint", "source_file"}
        missing = expected_columns - actual
        unexpected = actual - expected_columns
        violations = []
        if missing:
            violations.append(f"Missing columns: {sorted(missing)}")
        if unexpected:
            violations.append(f"Unexpected columns: {sorted(unexpected)}")
        return violations

    return QualityRule(
        rule_id="schema_drift",
        description="Column set must match registered schema contract",
        policy=Policy.BREAK,
        check_fn=check,
        remediation_runbook="docs/runbooks/schema_drift.md",
    )


# ── Volume anomaly check ──────────────────────────────────────────────────────

def make_volume_anomaly_check(
    baseline_counts: list[int],
    sigma: float = 2.0,
) -> QualityRule:
    mean = statistics.mean(baseline_counts) if baseline_counts else 0
    stdev = statistics.stdev(baseline_counts) if len(baseline_counts) > 1 else mean * 0.1

    def check(records: list[dict]) -> list[str]:
        count = len(records)
        lower = mean - sigma * stdev
        upper = mean + sigma * stdev
        if not (lower <= count <= upper):
            return [f"Volume {count} is outside ±{sigma}σ range [{lower:.0f}, {upper:.0f}] (baseline mean={mean:.0f})"]
        return []

    return QualityRule(
        rule_id="volume_anomaly",
        description=f"Row count must be within ±{sigma}σ of 7-day rolling baseline",
        policy=Policy.ALERT,
        check_fn=check,
        remediation_runbook="docs/runbooks/volume_anomaly.md",
    )


# ── Referential integrity check ───────────────────────────────────────────────

def make_ref_integrity_check(
    fk_field: str,
    parent_keys: set[Any],
) -> QualityRule:
    def check(records: list[dict]) -> list[str]:
        violations = []
        for r in records:
            val = r.get(fk_field)
            if val is not None and val not in parent_keys:
                violations.append(f"FK violation: {fk_field}={val} not found in parent")
        return violations[:10]  # cap at 10 examples

    return QualityRule(
        rule_id=f"ref_integrity_{fk_field}",
        description=f"Every '{fk_field}' value must exist in parent table",
        policy=Policy.BREAK,
        check_fn=check,
        remediation_runbook="docs/runbooks/referential_integrity.md",
    )


# ── PII detection check ───────────────────────────────────────────────────────

_PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),          # SSN
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # email
    re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),  # phone
]

def make_pii_check() -> QualityRule:
    def check(records: list[dict]) -> list[str]:
        violations = []
        for i, r in enumerate(records):
            for field, val in r.items():
                if field.startswith("_"):
                    continue
                for pattern in _PII_PATTERNS:
                    if pattern.search(str(val or "")):
                        violations.append(f"Row {i}: PII pattern detected in field '{field}'")
                        break
            if len(violations) >= 5:
                violations.append("... (additional violations truncated)")
                break
        return violations

    return QualityRule(
        rule_id="pii_in_gold",
        description="No PII patterns (SSN, email, phone) in Gold zone output",
        policy=Policy.BREAK,
        check_fn=check,
        remediation_runbook="docs/runbooks/pii_escape.md",
    )


# ── Run all checks ────────────────────────────────────────────────────────────

def run_checks(records: list[dict], rules: list[QualityRule]) -> list[QualityResult]:
    results = []
    for rule in rules:
        violations = rule.check_fn(records)
        passed = len(violations) == 0
        result = QualityResult(
            rule_id=rule.rule_id,
            policy=rule.policy,
            passed=passed,
            violations=violations,
        )
        results.append(result)
        if not passed:
            if rule.policy == Policy.BREAK:
                logger.error("BREAK — %s: %s | Runbook: %s", rule.rule_id, violations, rule.remediation_runbook)
            else:
                logger.warning("ALERT — %s: %s | Runbook: %s", rule.rule_id, violations, rule.remediation_runbook)

    return results


def has_break_violations(results: list[QualityResult]) -> bool:
    return any(r.policy == Policy.BREAK and not r.passed for r in results)
