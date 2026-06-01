# Fabrikam Retail — Data Engineering Initiative

Single Source of Truth lakehouse for 7 source systems. Eliminates double-counted revenue and unauditable CSV exports.

## Quick Start

```bash
# 1. Spin up Postgres with AdventureWorks
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run ingestion (batch example)
python -m bronze.ingestion.batch_ingestion

# 4. Run entity resolution
python -m silver.entity_resolution.matcher

# 5. Run quality scorecard
python -m quality.scorecard.eval_harness

# 6. Start MCP lineage server (stretch)
python -m mcp_server.lineage_server
```

## Architecture

**Medallion Lakehouse** — Bronze (raw) → Silver (conformed) → Gold (curated)

See [ADR.md](ADR.md) for full architectural decisions and rejected alternatives.

## Workstreams

| # | Name | Status | Owner |
|---|------|--------|-------|
| WS-1 | The Mess — Source Data | ✅ | DE-I |
| WS-2 | The Blueprint — ADR | ✅ | DA |
| WS-3 | The Intake — Ingestion | ✅ | DE-I |
| WS-4 | The Customer — Entity Resolution | ✅ | DE-T |
| WS-5 | The Tripwire — Quality Gates | ✅ | DQE |
| WS-6 | The Catalog | ✅ | PM/BA |
| WS-7 | The Scorecard — Eval Harness | ✅ | DQE |
| WS-8 | The Trace — MCP Lineage (stretch) | 🔧 | DE-T |
| WS-9 | The Swarm — Parallel Profiling (stretch) | 🔧 | DE-T |

## Source System Mapping (AdventureWorks → Fabrikam)

| AW Table | Fabrikam Source | Key | Injected Defects |
|----------|----------------|-----|-----------------|
| Sales.Customer + Person.Person | POS (legacy) | CustomerID | Timezone-stripped timestamps |
| Person.EmailAddress | E-Commerce | EmailAddress | Mixed-case, plus-address variants |
| Sales.SalesOrderHeader | POS Transactions | SalesOrderID | Local-time without offset |
| Person.Person (BusinessEntityID) | CRM (acquired) | BusinessEntityID | UTF-8/Latin-1 encoding collision |
| Sales.Store | Loyalty | BusinessEntityID | Leading-zero drops on codes |
| Sales.Customer (subset) | Merger Source A | CustomerID | Account_ID namespace collision |
| Person.Person (subset) | Merger Source B | BusinessEntityID | CUST_CODE varchar key |
| Person.Person (UUID-tagged) | Merger Source C | UUID | 40% null phone, 18% null address |

## Quality Gate Policy

| Check | Trigger | Policy |
|-------|---------|--------|
| Schema contract | Any Gold write | **BREAK** — PreToolUse hook |
| Null explosion | Column null rate > baseline+10pp | **BREAK** (key cols) / ALERT |
| Volume anomaly | Outside ±2σ 7-day rolling mean | ALERT |
| Referential integrity | FK violation Bronze→Silver | **BREAK** |
| Matcher regression | False-confidence +1pp vs main | **BREAK** (CI) |
| PII in Gold | PII pattern detected | **BREAK** + incident |

## Acceptance Criteria
- Golden record for ≥95% of transaction volume with field-level confidence scores
- Entity matcher: precision ≥0.92, recall ≥0.85, false-confidence ≤5%
- Any Gold value traceable to Bronze source row within 5 minutes
- Analyst can answer 5 business questions from catalogue + Gold alone
