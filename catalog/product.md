# Data Catalogue — Product

## What is this?
A **Product** is a single SKU sold by Fabrikam. The product catalogue covers all items across bicycle parts, accessories, and clothing lines.

## Where did it come from?
`Production.Product`, `Production.ProductSubcategory`, and `Production.ProductCategory` from AdventureWorks.

The product hierarchy is three levels: Category → Subcategory → Product.

## Can I trust it?
For current products, yes. For historical products (those with a `discontinued_date`), the pricing information reflects the last known price before discontinuation.

**Note:** Product prices in this table are list prices. Actual transaction prices may differ (promotional discounts are in the `Transaction` entity).

## What do the key terms mean?

**`product_line`**: Product family code. `R` = Road, `M` = Mountain, `T` = Touring, `S` = Standard.

**`list_price_usd`**: Manufacturer's recommended retail price in USD at the time of last update.

**`is_active`**: True if the product is currently available for sale.

## Upstream Producer Contract
Source: `Production.Product` (AdventureWorks Bronze ingestion)
