# Fabrikam Retail — Data Engineering Initiative

This repo implements a **Medallion Lakehouse** (Bronze / Silver / Gold) for Fabrikam Retail — a Single Source of Truth across 7 source systems. See `ADR.md` for all architectural decisions and rejected alternatives.

---

## Repo Layout

```
bronze/        Raw ingestion — append-only landing zone
silver/        Conformed transforms + golden customer record
gold/          Curated, analyst-facing, schema-contract-gated
quality/       DQ checks, PreToolUse hook, CI eval harness
catalog/       Business-facing data catalogue entries
mcp_server/    Lineage MCP server (WS-8 stretch)
swarm/         Parallel source profiling agents (WS-9 stretch)
data/          Defect inventory, source mappings, test fixtures
scripts/       Setup and utility scripts
console.py     Interactive pipeline console
ADR.md         Architecture Decision Record
```

---

## Zone Contracts

| Zone   | Mutation Policy               | Retention | PII                  | Who Reads                        |
|--------|-------------------------------|-----------|----------------------|----------------------------------|
| Bronze | Append-only — never update/delete | 7 years | Unmasked (access-controlled) | Platform engineers only |
| Silver | Insert or full overwrite on reprocess | 3 years | Pseudonymised at write | Data/ML engineers |
| Gold   | Schema-contract-gated writes ONLY | 2 years rolling | Fully masked or aggregated | Analysts, BI tools, applications |

### Bronze — Raw / Immutable
- Land data **exactly as received** — no cleaning, normalising, or transforming.
- Every Bronze record MUST carry these lineage fields:
  ```python
  { "source_system", "run_id", "ingested_at", "row_count", "schema_fingerprint", "source_file" }
  ```
- Retry failures are logged with `retry_count` + `error_type` per row.
- Flaky API sources use exponential backoff + circuit breaker + dead-letter logging.
- Rows failing after max retries go to `*_errors.jsonl` dead-letter — **never dropped**.
- Do NOT expose Bronze to analysts. They read Gold only.

### Silver — Conformed
- Insert or **full overwrite** on reprocess. No partial updates.
- Pseudonymise PII at write time using a reversible keyed hash (key in secrets manager, not in code).
- Every golden customer record carries **field-level confidence scores** (0.0–1.0).
- Every merge decision traces to a **named survivorship rule** — no anonymous merges.
- Entity matcher prompt MUST include ≥2 positive examples and ≥1 negative example (records that look similar but are provably different people). Confidence < 0.5 → manual review queue, do NOT merge.
- Survivorship precedence:
  ```
  email:       ecommerce > crm > pos
  phone:       crm > pos > loyalty
  address:     crm > merger_c > pos
  loyalty_num: loyalty (canonical — only source)
  name:        crm > pos  (UTF-8 normalised before comparison)
  ```

### Gold — Curated / Schema-Contract-Gated
- **Never write directly to Gold** without the PreToolUse hook passing (`quality/hook.py`).
- The hook validates: schema contract match, no PII patterns, null rates within threshold, volume within ±2σ baseline. Any BREAK = pipeline halts + audit log entry.
- Schema contracts are versioned JSON in `gold/schema_contracts/`. Changing a contract requires: version bump + ADR update (if breaking) + DQE PR review.
- No pipeline jargon in column names. All monetary values in USD (`_usd` suffix). Dates always UTC ISO-8601. No internal system IDs — use `customer_id` UUID only.

---

## Hard Rules (Non-Negotiables)

1. **Never write directly to Gold** without `quality/hook.py` passing.
2. **Every Bronze record** must carry the 6 lineage metadata fields.
3. **Every merge decision** must trace to a named survivorship rule in `silver/entity_resolution/survivorship.py`.
4. **Quality rules** live in `quality/checks.py` as declarative config — not buried in pipeline code.
5. **Entity matcher changes** require a CI scorecard run (`quality/scorecard/eval_harness.py`). A false-confidence rate increase >1pp blocks merge.
6. **All test fixtures** use AdventureWorks-derived data — no purely synthetic records.
7. **PII flow**: Bronze (unmasked, access-controlled) → Silver (pseudonymised) → Gold (fully masked/aggregated).

---

## Quality Gate Policy

| Check | Trigger | Policy | Runbook |
|-------|---------|--------|---------|
| Schema contract | Any Gold write | **BREAK** — PreToolUse hook | `docs/runbooks/schema_drift.md` |
| PII in Gold | PII pattern detected | **BREAK** + incident | `docs/runbooks/pii_escape.md` |
| Null explosion | Null rate > threshold | **BREAK** (key cols) / ALERT | `docs/runbooks/null_explosion.md` |
| Volume anomaly | Outside ±2σ rolling mean | ALERT | `docs/runbooks/volume_anomaly.md` |
| Referential integrity | FK violation Bronze→Silver | **BREAK** | `docs/runbooks/referential_integrity.md` |
| Matcher regression | False-confidence +1pp vs main | **BREAK** (CI) | — |

---

## Source System Map (AdventureWorks → Fabrikam)

| Source | AW Table | Key | Known Defects |
|--------|----------|-----|---------------|
| POS (legacy) | Sales.Customer + Person.Person | CustomerID (int) | INJ-POS-001: timezone-stripped timestamps; INJ-POS-002: key collision with Merger A |
| E-Commerce | Person.EmailAddress | EmailAddress | INJ-EC-001: mixed-case; INJ-EC-002: plus-address variants |
| CRM (acq. 2019) | Person.Person (BusinessEntityID) | BusinessEntityID | INJ-CRM-001: UTF-8/Latin-1 collision; INJ-CRM-002: address schema mismatch |
| Loyalty | Sales.Store | BusinessEntityID | INJ-LOY-001: leading zeros dropped; NATIVE-005: sparse demographics |
| Merger A (2021) | Sales.Customer subset | CustomerID (int) | INJ-MA-001: overlaps POS namespace |
| Merger B (2022) | Person.Person subset | BusinessEntityID | INJ-MB-001: free-form CUST_CODE |
| Merger C (2023) | Person.Person UUID-tagged | UUID v4 | INJ-MC-001: 40% null phone; INJ-MC-002: 18% null address |

Full defect taxonomy with few-shot contrasts and negative cases: `data/defect_inventory.md`.

---

## Working with Claude

- When writing code that touches more than one zone, state which zones are involved before starting.
- When adding a quality rule, assign BREAK or ALERT and link a remediation runbook.
- When changing the entity matcher or its prompt, run the scorecard and confirm no regression before committing.
- When in doubt about a zone boundary, check the Zone Contracts section above — do not guess.
