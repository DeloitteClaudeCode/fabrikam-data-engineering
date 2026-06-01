# Fabrikam Retail — Data Engineering Initiative
## Repo-Level Rules (Non-Negotiables)

### Architecture
This repo implements a **Medallion Lakehouse** (Bronze / Silver / Gold) for Fabrikam Retail.
See `ADR.md` for all architectural decisions and rejected alternatives.

### Zone Rules (Summary — see zone CLAUDE.md for details)
| Zone   | Mutation Policy               | PII       | Who Writes          |
|--------|-------------------------------|-----------|---------------------|
| Bronze | Append-only, immutable        | Unmasked  | Ingestion pipelines |
| Silver | Insert/overwrite on reprocess | Pseudonymised | Transform jobs  |
| Gold   | Schema-contract-gated ONLY    | Masked    | Approved jobs via hook |

**Before writing any zone-crossing code, read the target zone's CLAUDE.md.**

### Hard Rules
1. **Never write directly to Gold** without the PreToolUse schema-contract hook passing. See `quality/hook.py`.
2. **Every Bronze record** must carry lineage metadata: `source_system`, `run_id`, `ingested_at`, `row_count`, `schema_fingerprint`.
3. **Entity resolution decisions** must trace to a named survivorship rule. No anonymous merges.
4. **PII handling**: Bronze stores raw (access-controlled). Silver pseudonymises at write. Gold is fully masked or aggregated.
5. **Quality rules** live in `quality/checks.py` declarative config — not buried in pipeline code.

### Repo Layout
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
ADR.md         Architecture Decision Record
```

### Working with Claude
- Ask for zone-specific context before writing zone-crossing code.
- When adding a new quality rule, classify it as BREAK or ALERT and add a remediation runbook reference.
- Entity matcher changes require a CI scorecard run (see `quality/scorecard/`).
- All test fixtures use AdventureWorks-derived data — no purely synthetic records.
