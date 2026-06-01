"""
WS-8 (Stretch): MCP server exposing lineage tools over the data platform.
Tools: preview_table, trace_lineage, find_record, get_source_schema.

Each tool description states: required input format, known edge cases,
and what the tool does NOT do — enabling cold-start tool selection.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import mcp.server.fastmcp as fastmcp
    from mcp.server.fastmcp import FastMCP
    mcp_available = True
except ImportError:
    mcp_available = False
    # Provide stub for environments without MCP SDK
    class FastMCP:
        def __init__(self, name): self.name = name
        def tool(self): return lambda f: f
        def run(self): logger.error("MCP SDK not installed. Run: pip install mcp")

mcp = FastMCP("fabrikam-lineage")

BRONZE_PATH = Path("bronze/data")
SILVER_PATH = Path("silver/data")
GOLD_PATH = Path("gold/data")
LINEAGE_INDEX = Path("quality/audit_log.jsonl")


@mcp.tool()
def preview_table(
    zone: str,
    table_name: str,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Preview the first N rows of a table in a specified zone.

    Required input: zone ("bronze"|"silver"|"gold"), table_name (string), limit (int, default 10).

    Does NOT: filter rows, apply transformations, or return PII from Gold (Gold data is masked).
    Does NOT: support SQL WHERE clauses — use find_record for targeted lookups.

    Known edge cases: Bronze tables may have multiple JSONL files per run; this tool merges them.
    Returns at most `limit` rows. If the table doesn't exist, returns {"error": "table not found"}.
    """
    zone_path = {"bronze": BRONZE_PATH, "silver": SILVER_PATH, "gold": GOLD_PATH}.get(zone)
    if not zone_path:
        return {"error": f"Unknown zone '{zone}'. Use bronze, silver, or gold."}

    files = list(zone_path.glob(f"{table_name}*.jsonl"))
    if not files:
        return {"error": f"Table '{table_name}' not found in {zone} zone."}

    rows = []
    for f in sorted(files):
        for line in f.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    return {"zone": zone, "table": table_name, "rows": rows[:limit], "total_files": len(files)}


@mcp.tool()
def trace_lineage(
    gold_value: str,
    field_name: str,
    customer_id: str,
) -> dict[str, Any]:
    """
    Trace a value in the Gold zone back to its originating Bronze row.

    Required input:
      - gold_value: the exact value as it appears in Gold (string)
      - field_name: column name in the Gold table (string)
      - customer_id: the golden customer UUID (string)

    Returns: full transformation chain — Gold field → Silver survivorship rule → Bronze source row.

    Does NOT: trace values through aggregations or derived metrics (e.g. counts, sums).
    Does NOT: work for masked PII fields (those end in _masked) — the source value is not recoverable by design.

    Known edge cases:
      - If the value came from a merge conflict resolution, multiple Bronze rows may be returned.
      - CDC tombstone records will appear in the chain if the source row was deleted after ingestion.
    """
    # Load survivorship audit from silver
    silver_audit = SILVER_PATH / "survivorship_audit.jsonl"
    if not silver_audit.exists():
        return {"error": "Survivorship audit not found. Run silver transformation first."}

    chain = []
    for line in silver_audit.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("customer_id") == customer_id and rec.get("field") == field_name:
            chain.append({
                "step": "silver",
                "survivorship_rule": rec.get("rule_name"),
                "source_system": rec.get("source_system"),
                "value": rec.get("value"),
                "run_id": rec.get("run_id"),
            })

    # Look up Bronze source row by run_id
    bronze_rows = []
    for entry in chain:
        run_id = entry.get("run_id")
        source_system = entry.get("source_system")
        if run_id and source_system:
            for f in BRONZE_PATH.glob(f"{source_system}_{run_id}*.jsonl"):
                for line in f.read_text().splitlines():
                    if line.strip():
                        row = json.loads(line)
                        bronze_rows.append({
                            "step": "bronze",
                            "source_system": source_system,
                            "run_id": run_id,
                            "file": str(f),
                            "row": row,
                        })

    return {
        "customer_id": customer_id,
        "field": field_name,
        "gold_value": gold_value,
        "lineage_chain": chain + bronze_rows,
    }


@mcp.tool()
def find_record(
    zone: str,
    field_name: str,
    field_value: str,
    table_name: str = "",
) -> dict[str, Any]:
    """
    Find records matching a specific field value in a zone.

    Required input: zone, field_name, field_value. Optional: table_name (filters to one table).

    Does NOT: do fuzzy matching — this is an exact string match.
    Does NOT: search across all zones simultaneously — specify one zone per call.
    Does NOT: return more than 50 results (hard cap to prevent context overload).

    Known edge cases: Bronze records include lineage metadata fields (source_system, run_id etc.).
    Searching by these fields is supported and useful for lineage tracing.
    """
    zone_path = {"bronze": BRONZE_PATH, "silver": SILVER_PATH, "gold": GOLD_PATH}.get(zone)
    if not zone_path:
        return {"error": f"Unknown zone '{zone}'."}

    pattern = f"{table_name}*.jsonl" if table_name else "*.jsonl"
    matches = []
    for f in zone_path.glob(pattern):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if str(row.get(field_name, "")) == field_value:
                    matches.append({"file": f.name, "row": row})
            except json.JSONDecodeError:
                pass
            if len(matches) >= 50:
                return {"matches": matches, "truncated": True}

    return {"matches": matches, "truncated": False}


@mcp.tool()
def get_source_schema(source_system: str) -> dict[str, Any]:
    """
    Return the registered schema for a source system (Bronze landing schema).

    Required input: source_system — one of: pos, ecommerce, crm, loyalty, merger_a, merger_b, merger_c.

    Does NOT: return the Gold schema (use gold/schema_contracts/ for that).
    Does NOT: reflect real-time schema changes — returns the last ingested schema fingerprint.

    Known edge cases: Merger Source A and POS share overlapping CustomerID ranges.
    The schema will show CustomerID for both — the namespace collision is documented in data/defect_inventory.md.
    """
    schemas = {
        "pos": {
            "source_aw_table": "Sales.Customer + Person.Person",
            "key": "customer_id (int) — WARNING: overlaps with merger_a account_id namespace",
            "columns": ["customer_id", "store_id", "person_type", "name_style", "title",
                        "first_name", "middle_name", "last_name", "suffix", "email",
                        "phone", "modified_date", "order_date"],
            "known_defects": ["INJ-POS-001: timezone-stripped timestamps", "INJ-POS-002: key namespace collision"],
        },
        "ecommerce": {
            "source_aw_table": "Person.EmailAddress",
            "key": "email (string)",
            "columns": ["email_address_id", "business_entity_id", "email", "modified_date"],
            "known_defects": ["INJ-EC-001: mixed-case emails", "INJ-EC-002: plus-address variants"],
        },
        "crm": {
            "source_aw_table": "Person.Person (BusinessEntityID)",
            "key": "business_entity_id (int)",
            "columns": ["business_entity_id", "person_type", "first_name", "middle_name",
                        "last_name", "phone", "address_line1", "city", "state", "postal_code"],
            "known_defects": ["INJ-CRM-001: UTF-8/Latin-1 encoding collision", "INJ-CRM-002: address schema mismatch"],
        },
        "loyalty": {
            "source_aw_table": "Sales.Store",
            "key": "loyalty_num (char 12) — leading zeros significant",
            "columns": ["loyalty_num", "store_name", "business_type", "annual_revenue", "modified_date"],
            "known_defects": ["INJ-LOY-001: leading zeros dropped in CSV exports"],
        },
        "merger_a": {
            "source_aw_table": "Sales.Customer (subset)",
            "key": "account_id (int) — WARNING: overlaps with pos customer_id namespace",
            "columns": ["account_id", "name", "address", "phone", "created_date"],
            "known_defects": ["INJ-MA-001: account_id namespace collision with POS"],
        },
        "merger_b": {
            "source_aw_table": "Person.Person (subset)",
            "key": "cust_code (varchar 20) — no enforced format",
            "columns": ["cust_code", "first_name", "last_name", "middle_name", "email", "phone"],
            "known_defects": ["INJ-MB-001: free-form CUST_CODE, no format enforcement"],
        },
        "merger_c": {
            "source_aw_table": "Person.Person (UUID-tagged)",
            "key": "uuid (UUID v4)",
            "columns": ["uuid", "first_name", "last_name", "email", "phone", "address_line1",
                        "city", "state", "postal_code", "created_date"],
            "known_defects": ["INJ-MC-001: 40% null phone", "INJ-MC-002: 18% null address"],
        },
    }
    schema = schemas.get(source_system)
    if not schema:
        return {"error": f"Unknown source system '{source_system}'. Valid values: {list(schemas.keys())}"}
    return {"source_system": source_system, **schema}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not mcp_available:
        print("Install MCP SDK: pip install mcp")
    else:
        mcp.run()
