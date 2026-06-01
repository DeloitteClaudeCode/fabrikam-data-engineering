# Data Catalogue — Loyalty Account

## What is this?
A **Loyalty Account** represents a customer's enrolment in the Fabrikam Rewards programme. One loyalty account = one `loyalty_num` = one customer (after de-duplication).

The loyalty account is the most reliable bridge between in-store and online spending because the loyalty card is scanned at both channels. It is **not** the primary customer identifier — always join via the golden `customer_id`.

## Where did it come from?
Mapped from `Sales.Store` (BusinessEntityID used as loyalty identifier) in AdventureWorks, supplemented by the loyalty platform's own flat file exports.

**Known defect:** Leading zeros were historically dropped in CSV exports from the loyalty platform. The pipeline restores them. If you see a loyalty number shorter than 12 characters, it indicates the restore failed — raise a data quality ticket.

## Can I trust it?
Yes, for customers who have presented their loyalty card. Approximately 62% of transactions are linked to a loyalty account. The remaining 38% are anonymous.

## What do the key terms mean?

**`loyalty_num`**: Always 12 characters, zero-padded (e.g. `000000000042`). This is the canonical form — do not strip leading zeros.

**`loyalty_segment`**: The customer's current tier based on the last 12 months of spend. See the Customer catalogue entry for tier definitions. Segment is recalculated monthly.

**`lifetime_points`**: Total points accumulated since account creation. Not adjusted for point expiry. Use `active_points` for redeemable balance.

**`linked_customer_id`**: The golden `customer_id` from the Customer entity. NULL means the loyalty account has not yet been matched to a golden record (pending entity resolution run).

## Upstream Producer Contract
Source: Loyalty flat file export + `Sales.Store` Bronze ingestion  
Survivorship: Loyalty number is canonical — only source for this field (`silver/entity_resolution/survivorship.py`)
