"""
WS-3: Batch file ingestion — lands raw data in Bronze with lineage metadata.
Implements validation-retry loop: parse → validate → retry on error (max N attempts).

Sources: POS CSV, CRM XML export, Loyalty flat file.
"""

import csv
import io
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .lineage import attach_lineage, make_lineage

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


@dataclass
class ParseResult:
    records: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class ValidationError:
    row_index: int
    field: str
    message: str
    raw_value: Any


def validate_pos_record(row: dict, idx: int) -> list[ValidationError]:
    """Validate a POS record. Returns list of errors (empty = valid)."""
    errors = []
    # CustomerID must be positive integer
    cid = row.get("customer_id", "")
    if not str(cid).strip().lstrip("-").isdigit() or int(cid) <= 0:
        errors.append(ValidationError(idx, "customer_id", "must be positive integer", cid))
    # order_date must be present (may lack timezone — that's a known defect, log but don't reject)
    if not row.get("order_date"):
        errors.append(ValidationError(idx, "order_date", "missing required field", None))
    return errors


def validate_crm_record(row: dict, idx: int) -> list[ValidationError]:
    errors = []
    if not row.get("business_entity_id"):
        errors.append(ValidationError(idx, "business_entity_id", "missing required field", None))
    return errors


def parse_csv_with_retry(
    raw_content: str,
    source_system: str,
    validator: Callable[[dict, int], list[ValidationError]],
    max_retries: int = MAX_RETRIES,
) -> ParseResult:
    """
    Validation-retry loop:
    1. Parse CSV
    2. Validate each row
    3. On validation error, feed specific error back and retry the row (up to max_retries)
    """
    result = ParseResult()
    reader = csv.DictReader(io.StringIO(raw_content))
    rows = list(reader)

    for idx, row in enumerate(rows):
        row = {k.lower().strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
        errors = validator(row, idx)

        retry = 0
        while errors and retry < max_retries:
            retry += 1
            # Feed specific error back — attempt auto-remediation per error type
            row = _attempt_remediation(row, errors, source_system)
            errors = validator(row, idx)
            logger.debug("Row %d retry %d/%d: %s", idx, retry, max_retries, [e.message for e in errors])

        result.retry_count += retry

        if errors:
            for e in errors:
                result.errors.append({
                    "row_index": idx,
                    "field": e.field,
                    "error": e.message,
                    "raw_value": str(e.raw_value),
                    "retry_count": retry,
                })
        else:
            result.records.append(row)

    return result


def _attempt_remediation(row: dict, errors: list[ValidationError], source: str) -> dict:
    """Rule-based remediation fed back by specific validation errors."""
    for e in errors:
        if e.field == "customer_id":
            # Strip leading/trailing whitespace and non-numeric chars
            raw = str(row.get("customer_id", "")).strip()
            cleaned = "".join(c for c in raw if c.isdigit())
            if cleaned:
                row["customer_id"] = int(cleaned)
        if e.field == "loyalty_num" and source == "loyalty":
            # Restore leading zeros to 12-char field
            row["loyalty_num"] = str(row.get("loyalty_num", "")).zfill(12)
        if e.field == "email" and source == "ecommerce":
            row["email"] = str(row.get("email", "")).lower().strip()
    return row


def ingest_batch_file(
    file_path: str | Path,
    source_system: str,
    validator: Callable[[dict, int], list[ValidationError]],
    bronze_output_path: str | Path,
) -> dict[str, Any]:
    """
    Land a batch file in Bronze with lineage metadata.
    Returns a run summary.
    """
    file_path = Path(file_path)
    raw_content = file_path.read_text(encoding="utf-8", errors="replace")

    result = parse_csv_with_retry(raw_content, source_system, validator)

    columns = [(k, "string") for k in result.records[0].keys()] if result.records else []
    lineage = make_lineage(
        source_system=source_system,
        source_file=str(file_path),
        row_count=len(result.records),
        columns=columns,
    )

    records_with_lineage = attach_lineage(result.records, lineage)

    output = Path(bronze_output_path)
    output.mkdir(parents=True, exist_ok=True)
    out_file = output / f"{source_system}_{lineage['run_id']}.jsonl"
    with out_file.open("w") as f:
        for r in records_with_lineage:
            f.write(json.dumps(r) + "\n")
        # dead-letter errors
        if result.errors:
            dead_letter = output / f"{source_system}_{lineage['run_id']}_errors.jsonl"
            with dead_letter.open("w") as df:
                for e in result.errors:
                    df.write(json.dumps({**e, **lineage}) + "\n")

    summary = {
        "run_id": lineage["run_id"],
        "source_system": source_system,
        "records_landed": len(result.records),
        "errors": len(result.errors),
        "total_retries": result.retry_count,
        "output_file": str(out_file),
    }
    logger.info("Batch ingestion complete: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Example usage with test fixture
    import sys
    if len(sys.argv) >= 4:
        ingest_batch_file(sys.argv[1], sys.argv[2], validate_pos_record, sys.argv[3])
