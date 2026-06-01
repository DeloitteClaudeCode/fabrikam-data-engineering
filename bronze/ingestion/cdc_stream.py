"""
WS-3: CDC stream ingestion (Kafka-style) — lands change events in Bronze with lineage.
Simulates CRM CDC feed: INSERT/UPDATE/DELETE events keyed by BusinessEntityID.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .lineage import attach_lineage, make_lineage

logger = logging.getLogger(__name__)


@dataclass
class CdcEvent:
    op: str          # I = insert, U = update, D = delete
    before: dict | None
    after: dict | None
    ts_ms: int       # event timestamp in milliseconds
    source_system: str
    topic: str


def parse_cdc_event(raw: dict) -> CdcEvent:
    """Parse a Debezium-style CDC event."""
    payload = raw.get("payload", raw)
    return CdcEvent(
        op=payload.get("op", "r"),
        before=payload.get("before"),
        after=payload.get("after"),
        ts_ms=payload.get("ts_ms", 0),
        source_system=payload.get("source", {}).get("db", "unknown"),
        topic=raw.get("topic", "unknown"),
    )


def process_cdc_batch(
    events: list[dict],
    source_system: str,
    bronze_output_path: str | Path,
    topic: str = "crm.person",
) -> dict[str, Any]:
    """
    Process a batch of CDC events and land them in Bronze.
    Inserts and updates land as-is. Deletes are tombstoned (not removed — Bronze is immutable).
    """
    parsed = [parse_cdc_event(e) for e in events]

    # Bronze record = the after-image (for I/U) or tombstone marker (for D)
    records = []
    for ev in parsed:
        record = ev.after.copy() if ev.after else {}
        record["_cdc_op"] = ev.op
        record["_cdc_ts_ms"] = ev.ts_ms
        record["_cdc_topic"] = ev.topic
        if ev.op == "d":
            record["_cdc_tombstone"] = True
            record["_cdc_before"] = json.dumps(ev.before)
        records.append(record)

    columns = [(k, "string") for k in records[0].keys()] if records else []
    lineage = make_lineage(
        source_system=source_system,
        source_file=topic,
        row_count=len(records),
        columns=columns,
    )
    attach_lineage(records, lineage)

    output = Path(bronze_output_path)
    output.mkdir(parents=True, exist_ok=True)
    out_file = output / f"{source_system}_cdc_{lineage['run_id']}.jsonl"
    with out_file.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    summary = {
        "run_id": lineage["run_id"],
        "source_system": source_system,
        "events_processed": len(records),
        "inserts": sum(1 for e in parsed if e.op == "i"),
        "updates": sum(1 for e in parsed if e.op == "u"),
        "deletes": sum(1 for e in parsed if e.op == "d"),
        "output_file": str(out_file),
    }
    logger.info("CDC batch complete: %s", summary)
    return summary
