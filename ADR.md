# Architecture Decision Record
## Fabrikam Retail — Single Source of Truth Lakehouse
**Status:** Approved  **Date:** June 2026  **Owner:** Chief Data Officer

---

## Decision: Medallion Lakehouse (Bronze / Silver / Gold)

### Context
Fabrikam operates 7 source systems with no shared customer key, conflicting encodings, and no lineage. Analysts rely on ad-hoc CSV exports producing unauditable results. The CDO has mandated a Single Source of Truth.

### Chosen Architecture
Three-zone Medallion Lakehouse on cloud object storage (S3-compatible) with Delta Lake / Apache Iceberg for ACID semantics and time-travel.

| Layer       | Technology                      | Rationale |
|-------------|----------------------------------|-----------|
| Object Store | S3-compatible blob store        | Decouples compute/storage; cost-effective |
| Table Format | Delta Lake or Apache Iceberg    | ACID, time-travel, schema evolution |
| Ingestion   | Apache Spark + Kafka CDC         | Handles batch, CDC, flaky APIs uniformly |
| Orchestration | Apache Airflow / Dagster        | DAG-native retry; observable |
| Entity Resolution | Claude-assisted + deterministic rules | ML recall + auditable output |
| Catalogue   | Apache Atlas / OpenMetadata      | Open standard; lineage graphs |
| Quality     | Great Expectations + custom hooks | Declarative contracts |
| Serving     | Trino / Databricks SQL           | Federation across zones; analyst-friendly SQL |

### Zone Definitions

| Zone   | Mutation Policy       | Retention | PII Handling            | Readers                   |
|--------|-----------------------|-----------|-------------------------|---------------------------|
| Bronze | Append-only (immutable) | 7 years | Unmasked (access-controlled) | Platform engineers only |
| Silver | Insert/overwrite on reprocess | 3 years | Pseudonymised at write | Data/ML engineers |
| Gold   | Schema-contract-gated writes only | 2 years rolling | Fully masked or aggregated | Analysts, BI, applications |

---

## What We Deliberately Chose NOT To Do

### 1. Federated Data Mesh
**Rejected because:** Mesh requires stable domain ownership. Fabrikam's data ownership is unclear across 3 acquired companies. Coordination overhead would delay delivery by 6+ months before a single record is governed.  
**Revisit when:** Zone ownership is stable (post Phase 3) and domain teams are identified.

### 2. Traditional Data Warehouse as Landing Zone
**Rejected because:** Ingesting raw data directly into a warehouse destroys raw fidelity. We need Bronze immutability for reprocessing — warehouse UPSERT semantics conflict with append-only requirements.  
**Revisit when:** Never for landing. Warehouse SQL layer (Trino/Databricks) sits on top of the lakehouse for serving only.

### 3. Real-time Streaming as Default
**Rejected because:** Most sources are batch (file exports, nightly CDC). Defaulting to streaming adds operational complexity (Kafka consumer groups, offset management, backpressure) for marginal latency gains on batch sources.  
**Decision:** Streaming is added per-source only when business latency requirements are documented and approved.

### 4. Proprietary Managed Catalogue (e.g., Collibra, Alation)
**Rejected because:** Vendor lock-in and cost. Open standards (Atlas/OpenMetadata) give equivalent lineage graphs at a fraction of the cost and allow future portability.

---

## CLAUDE.md Hierarchy

```
CLAUDE.md                  ← Repo root: overall pattern, non-negotiables
bronze/CLAUDE.md           ← Bronze zone: append-only, lineage requirements
silver/CLAUDE.md           ← Silver zone: pseudonymisation, survivorship rules
gold/CLAUDE.md             ← Gold zone: schema-contract gate, masking policy
```

A fresh Claude session given only the root `CLAUDE.md` should ask for zone-specific context before writing zone-crossing code. This is tested in the CI contract test suite.
