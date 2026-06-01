# Data Catalogue — Transaction

## What is this?
A **Transaction** is a single sales event — one purchase made by one customer at one point in time. This includes both in-store (POS) and online (e-commerce) purchases.

Transactions are linked to the golden Customer record using `customer_id`. If you see a transaction without a `customer_id`, the purchase was anonymous (loyalty card not presented, no account login).

## Where did it come from?
- `Sales.SalesOrderHeader` and `Sales.SalesOrderDetail` from AdventureWorks (POS)
- E-commerce order feed (CDC stream)

**Known issue at source:** POS timestamps were recorded in server-local time without a timezone offset. The ingestion pipeline normalises these to UTC using the store's known timezone. Transactions from before 2022 may have ±1 hour uncertainty during DST transitions.

## Can I trust it?
Yes, for revenue totals. The entity resolution process (WS-4) eliminated ~12% double-counting that existed in the old CSV exports by de-duplicating customers across POS and e-commerce.

`total_amount_usd` is always in USD. Historical transactions in other currencies have been converted using the exchange rate on the transaction date.

## What do the key terms mean?

**`channel`**: Where the purchase happened. Values: `in_store`, `online`, `mobile_app`.

**`is_returned`**: True if this transaction was subsequently fully refunded. Partial refunds are not flagged here — see the `Refund` entity.

**`store_id`**: References the `Store` entity. NULL for online transactions.

## Upstream Producer Contract
Source: `Sales.SalesOrderHeader` via Bronze ingestion (`bronze/ingestion/batch_ingestion.py`)
