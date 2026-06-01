"""Lineage metadata attached to every Bronze record."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


def schema_fingerprint(columns: list[tuple[str, str]]) -> str:
    """SHA-256 of sorted column name+type pairs."""
    payload = json.dumps(sorted(columns), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def make_lineage(
    source_system: str,
    source_file: str,
    row_count: int,
    columns: list[tuple[str, str]],
    run_id: str | None = None,
) -> dict[str, Any]:
    return {
        "source_system": source_system,
        "run_id": run_id or str(uuid.uuid4()),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "row_count": row_count,
        "schema_fingerprint": schema_fingerprint(columns),
        "source_file": source_file,
    }


def attach_lineage(records: list[dict], lineage: dict[str, Any]) -> list[dict]:
    """Attach lineage fields to every record."""
    for r in records:
        r.update(lineage)
    return records
