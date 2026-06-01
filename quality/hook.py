"""
WS-5: PreToolUse hook — blocks any write to the Gold zone until schema contract passes.
Logs the blocking rule and failing check for auditability.

This module is invoked as a Claude Code PreToolUse hook (configured in .claude/settings.json).
It can also be called directly from pipeline code before any Gold write.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checks import (
    Policy,
    QualityRule,
    QualityResult,
    has_break_violations,
    make_null_rate_check,
    make_pii_check,
    make_schema_drift_check,
    run_checks,
)

logger = logging.getLogger(__name__)

AUDIT_LOG = Path("quality/audit_log.jsonl")


def load_schema_contract(table_name: str) -> dict:
    """Load the registered schema contract for a Gold table."""
    contract_path = Path(f"gold/schema_contracts/{table_name}.json")
    if not contract_path.exists():
        raise FileNotFoundError(f"No schema contract registered for table '{table_name}'. Register one in gold/schema_contracts/ before writing.")
    return json.loads(contract_path.read_text())


def build_gold_rules(table_name: str, records: list[dict]) -> list[QualityRule]:
    """Build the quality rule set for a Gold zone write."""
    contract = load_schema_contract(table_name)
    expected_columns = set(contract.get("columns", {}).keys())

    rules = [
        make_schema_drift_check(expected_columns),
        make_pii_check(),
    ]

    # Null rules from contract
    for col, spec in contract.get("columns", {}).items():
        if spec.get("nullable") is False:
            rules.append(make_null_rate_check(col, threshold=0.0, policy=Policy.BREAK, key_column=True))
        elif spec.get("null_threshold"):
            rules.append(make_null_rate_check(col, threshold=spec["null_threshold"], policy=Policy.ALERT, key_column=False))

    return rules


def check_gold_write(table_name: str, records: list[dict]) -> tuple[bool, list[QualityResult]]:
    """
    Gate function: returns (allowed, results).
    If allowed=False, the write must be blocked.
    """
    rules = build_gold_rules(table_name, records)
    results = run_checks(records, rules)
    allowed = not has_break_violations(results)

    # Audit log every gate evaluation
    audit_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "table": table_name,
        "allowed": allowed,
        "record_count": len(records),
        "results": [
            {
                "rule_id": r.rule_id,
                "policy": r.policy.value,
                "passed": r.passed,
                "violations": r.violations,
            }
            for r in results
        ],
    }
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(audit_entry) + "\n")

    if not allowed:
        failing = [r for r in results if r.policy == Policy.BREAK and not r.passed]
        logger.error(
            "GOLD WRITE BLOCKED for table '%s'. Failing rules: %s",
            table_name,
            [r.rule_id for r in failing],
        )

    return allowed, results


# ── Claude Code PreToolUse hook entrypoint ────────────────────────────────────
# Called by the harness with tool_input on stdin as JSON.

def preToolUse_hook():
    """
    Hook handler for Claude Code PreToolUse.
    Reads tool input from stdin, blocks Gold writes that fail schema contracts.
    Exit 0 = allow. Exit 2 = block (output message shown to Claude).
    """
    tool_input = json.loads(sys.stdin.read())
    tool_name = tool_input.get("tool_name", "")
    params = tool_input.get("tool_input", {})

    # Only gate write-type tools targeting the gold/ path
    target_path = params.get("file_path", params.get("path", ""))
    if "gold/" not in str(target_path) and "gold\\" not in str(target_path):
        sys.exit(0)

    # Extract table name from path
    parts = Path(target_path).parts
    try:
        gold_idx = next(i for i, p in enumerate(parts) if p == "gold")
        table_name = parts[gold_idx + 1] if gold_idx + 1 < len(parts) else "unknown"
    except StopIteration:
        table_name = "unknown"

    # Try to parse records from tool content
    content = params.get("content", "")
    records = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not records:
        # No parseable records — allow but warn
        print(json.dumps({"reason": f"Gold write to '{table_name}' has no parseable records — write allowed but not validated."}))
        sys.exit(0)

    allowed, results = check_gold_write(table_name, records)
    if not allowed:
        failing = [r for r in results if r.policy == Policy.BREAK and not r.passed]
        msg = f"BLOCKED: Gold write to '{table_name}' failed schema contract. Rules: {[r.rule_id for r in failing]}. Check quality/audit_log.jsonl for details."
        print(json.dumps({"reason": msg}))
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    preToolUse_hook()
