# Data Catalogue — Customer (Golden Record)

## What is this?
The **Customer** entity is Fabrikam's canonical, merged representation of a real person who has interacted with the business. One row in this table = one physical human being, regardless of how many source systems they appear in.

This is the output of the entity resolution process (WS-4). It supersedes all source-system customer records for reporting purposes.

## Where did it come from?
Built from seven source systems:

| Source | Contribution |
|--------|-------------|
| POS (legacy) | Transaction history, name, address |
| E-Commerce | Email address (most reliable) |
| Loyalty | Loyalty number, segment, spend history |
| CRM (acquired 2019) | Full address, phone, marketing preferences |
| Merger Source A (2021) | Additional transaction history |
| Merger Source B (2022) | Secondary contact details |
| Merger Source C (2023) | Most recent registration data |

Each field in this table has a `_source` column indicating which system's value won (e.g. `email_source = 'ecommerce'`).

## Can I trust it?
The `record_confidence` column tells you. It's a number from 0.0 to 1.0:

| Score | What it means |
|-------|--------------|
| 0.85+ | High confidence — multiple corroborating sources |
| 0.5–0.85 | Moderate — use with care for decisions |
| < 0.5 | Low — record is in the manual review queue, **do not use for marketing** |

Only records with `record_confidence ≥ 0.5` are published to Gold. Lower-confidence records remain in Silver pending review.

## What do the key terms mean?

**`loyalty_segment`**: Assigned by the Loyalty programme based on 12-month spend. Values:
- `Bronze` — spend < $500/year
- `Silver` — $500–$2,000/year
- `Gold` — $2,000–$5,000/year
- `Platinum` — > $5,000/year

**`email_masked`**: For privacy, the full email is not stored in Gold. The masked format is `jo**@gmail.com` (first 2 chars + domain).

**`source_systems`**: Comma-separated list of systems that contributed to this golden record (e.g. `"pos,ecommerce,crm"`).

## What does this table NOT contain?
- Raw PII (full email, phone, SSN) — those are in Silver (restricted access)
- Source-system internal IDs (POS_CUST_ID, BusinessEntityID) — use the `customer_id` UUID only
- Transaction data — see the `Transaction` entity

## Upstream Producer Contract
Schema contract: [`gold/schema_contracts/customer.json`](../gold/schema_contracts/customer.json)  
Survivorship rules: [`silver/entity_resolution/survivorship.py`](../silver/entity_resolution/survivorship.py)
