# Data Catalogue — Store

## What is this?
A **Store** is a physical Fabrikam retail location. Used to attribute in-store transactions to a location and to manage the loyalty programme's store-level reporting.

## Where did it come from?
`Sales.Store` from AdventureWorks.

**Known defect (native):** Demographics fields (`Revenue`, `BusinessType`) are sparse — approximately 20% of stores have nulls here. This is a known gap in the source data, not a pipeline error.

## Can I trust it?
For store identification (name, address, region), yes — these are well-populated. For store demographics, use with caution and check for nulls.

## What do the key terms mean?

**`business_type`**: Operating model. Values: `Specialty` (dedicated bike shop), `Value` (discount retailer), `Warehouse` (bulk/wholesale).

**`annual_revenue_band`**: Revenue tier. `Low` = <$1M, `Medium` = $1M–$5M, `High` = >$5M. Derived from the sparse `Revenue` field; NULL where source data is missing.

**`loyalty_code`**: The store's identifier in the loyalty programme. **Important:** Leading zeros are significant in this code (e.g. `000042` and `42` are different stores). The pipeline restores leading zeros stripped by legacy CSV exports.

## Upstream Producer Contract
Source: `Sales.Store` (AdventureWorks Bronze ingestion)
