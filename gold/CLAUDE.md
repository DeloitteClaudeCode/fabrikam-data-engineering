# Gold Zone — CLAUDE.md

## Zone Contract: CURATED / SCHEMA-CONTRACT-GATED

**Mutation Policy:** Schema-contract-gated writes ONLY. The PreToolUse hook in `quality/hook.py` MUST pass before any write.  
**Retention:** 2 years rolling.  
**PII:** Fully masked or aggregated. Zero raw PII permitted.  
**Who Reads:** Analysts, BI tools, applications.

## CRITICAL: No Direct Writes
**Never write to Gold without the schema contract hook passing.**  
The hook (`quality/hook.py`) validates:
1. Column names and types match the registered schema contract
2. No PII patterns detected in output
3. Null rates within configured thresholds
4. Volume within ±2σ of 7-day rolling baseline

Any failing check = BREAK. The pipeline halts and logs the failing rule.

## Schema Contract Location
Contracts are versioned JSON files in `gold/schema_contracts/`.  
Changing a contract requires: (1) version bump, (2) ADR update if breaking, (3) PR review by DQE.

## Rules
- Gold tables are the analyst's interface — no pipeline jargon in column names.
- All monetary values in a single currency (USD) with explicit column suffix `_usd`.
- Date columns always UTC, ISO-8601.
- No join keys that expose internal system IDs — use the golden `customer_id` only.
