# Bronze Zone — CLAUDE.md

## Zone Contract: RAW / IMMUTABLE

**Mutation Policy:** Append-only. Never update or delete Bronze records.  
**Retention:** 7 years.  
**PII:** Unmasked — raw as received. Access is restricted to platform engineers.  
**Who Reads:** Platform engineers, ingestion pipeline code only.

## Required Lineage Metadata (Every Record)
Every row landing in Bronze MUST carry:
```python
{
    "source_system": str,       # e.g. "pos", "ecommerce", "crm"
    "run_id": str,              # UUID for the ingestion run
    "ingested_at": str,         # ISO-8601 UTC timestamp
    "row_count": int,           # rows in this batch
    "schema_fingerprint": str,  # SHA-256 of column names+types
    "source_file": str,         # originating file/topic/endpoint
}
```

## Rules
- Do NOT clean, transform, or normalise data in Bronze. Land it exactly as received.
- Do NOT expose Bronze tables to analysts. They read Gold only.
- Retry failures must be logged with `retry_count` and `error_type` per row.
- Flaky API ingestion must implement exponential backoff + dead-letter logging.
- If validation fails after max retries, route to `bronze.dead_letter` — never drop.
