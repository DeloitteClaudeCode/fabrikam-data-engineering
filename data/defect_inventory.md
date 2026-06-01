# WS-1: Defect Inventory
## AdventureWorks → Fabrikam Source Mapping & Injected Defects

Each defect is keyed to its source system, AW table origin, and defect category.

---

## Native AdventureWorks Noise (present in source data, NOT injected)

| Defect ID | AW Table | Source System | Description | Category |
|-----------|----------|---------------|-------------|----------|
| NATIVE-001 | Person.Person | CRM / POS | Sparse phone fields (`Phone` is NULL for ~30% of BusinessEntity rows) | Completeness |
| NATIVE-002 | Person.Address | CRM / POS | Mixed address casing ("123 Main St" vs "123 MAIN ST") | Format |
| NATIVE-003 | Sales.Customer | POS / Merger A | CustomerID and BusinessEntityID are separate key spaces that overlap in value range | Key collision |
| NATIVE-004 | Person.Person | All | MiddleName is NULL for most records; when present, free-form (initials, full name, none) | Completeness |
| NATIVE-005 | Sales.Store | Loyalty | Demographics (Revenue, BusinessType) sparse for ~20% of stores | Completeness |

---

## Injected Defects (added to simulate real-world noise not in AdventureWorks)

### POS (Sales.Customer + Person.Person)

| Defect ID | Description | Few-Shot Contrast | Root Cause Simulated |
|-----------|-------------|-------------------|----------------------|
| INJ-POS-001 | Timestamps recorded in server-local time without timezone offset | **Good bad data:** `2024-03-15 14:32:17` (no offset, ambiguous DST); **Bad bad data:** `9999-99-99 99:99:99` (no real system emits this) | POS server configured in PST; clock not UTC-normalised |
| INJ-POS-002 | POS_CUST_ID namespace collision with Merger Source A Account_IDs | **Good bad data:** CustomerID=10001 exists in both POS and Merger A with different people; **Bad bad data:** CustomerID=-1 or CustomerID=999999999 (outside realistic range) | Integer key reuse across acquired systems |

### E-Commerce (Person.EmailAddress)

| Defect ID | Description | Few-Shot Contrast |
|-----------|-------------|-------------------|
| INJ-EC-001 | Mixed-case email addresses | **Good:** `John.Doe@Contoso.COM` vs `john.doe@contoso.com` (same mailbox, different casing); **Bad:** `@@@invalid` (no real system stores this) |
| INJ-EC-002 | RFC 5321 plus-addressing variants | **Good:** `john+loyalty@contoso.com` and `john@contoso.com` resolve to same mailbox; **Bad:** `john@@contoso.com` |

### CRM (Person.Person via BusinessEntityID)

| Defect ID | Description | Few-Shot Contrast |
|-----------|-------------|-------------------|
| INJ-CRM-001 | UTF-8 / Latin-1 encoding collision on Name columns | **Good bad data:** `Müller` stored as `MÃ¼ller` (Latin-1 byte sequence misread as UTF-8); **Bad bad data:** `????` (placeholder — no real system emits literal question marks for names) |
| INJ-CRM-002 | Address schema format differs from Sales schema | **Good:** CRM uses `AddressLine1 + City + StateProvince` concatenated; POS uses separate columns | Different ETL schemas across acquisition |

### Loyalty (Sales.Store)

| Defect ID | Description | Few-Shot Contrast |
|-----------|-------------|-------------------|
| INJ-LOY-001 | Leading zeros dropped from loyalty codes in CSV exports | **Good bad data:** `LOYALTY_NUM=000042` exported as `42` (Excel auto-numeric conversion); **Bad bad data:** `LOYALTY_NUM=ABCXYZ` (wrong type entirely) |

### Merger Source A (Sales.Customer subset)

| Defect ID | Description | Few-Shot Contrast |
|-----------|-------------|-------------------|
| INJ-MA-001 | Account_ID integer namespace overlaps POS_CUST_ID | **Good bad data:** Account_ID=5432 in Merger A and CustomerID=5432 in POS are different people; **Bad bad data:** Account_ID=0 or negative (unrealistic for this system) |

### Merger Source B (Person.Person subset)

| Defect ID | Description | Few-Shot Contrast |
|-----------|-------------|-------------------|
| INJ-MB-001 | Free-form CUST_CODE varchar with no enforced format | **Good bad data:** `CUST_CODE` values like `"ADV-1001"`, `"1001"`, `"ADV1001"` all referring to same customer | No format validation at source |

### Merger Source C (Person.Person UUID-tagged)

| Defect ID | Description | Few-Shot Contrast |
|-----------|-------------|-------------------|
| INJ-MC-001 | 40% null phone numbers | **Good bad data:** Phone=NULL (customer never provided it); **Bad bad data:** Phone=`0000000000` (dummy fill — Merger C specifically does NOT do this) |
| INJ-MC-002 | 18% null address lines | **Good bad data:** AddressLine1=NULL (incomplete registration); **Bad bad data:** AddressLine1=`N/A` (Merger C uses NULL, not sentinel strings) |

---

## Negative Cases (Records That Look Similar But Are Different People)

These are required for the entity matcher prompt (WS-4). Two records must NOT be merged.

| Neg Case ID | Source | Record A | Record B | Why They're Different |
|-------------|--------|----------|----------|----------------------|
| NEG-001 | POS vs Merger A | CustomerID=5432, Name="James Wilson", DOB=1978 | Account_ID=5432, Name="James Wilson", DOB=1965 | Same key + name, different date of birth — namespace collision, two real people |
| NEG-002 | POS vs CRM | CustomerID=8901, Address="123 Oak St, Portland OR" | BusinessEntityID=8901, Address="123 Oak St, Portland ME" | Same street + ID, different state — two different cities named Portland |
| NEG-003 | E-Commerce vs CRM | Email=`robert.smith@gmail.com` | Name="Robert Smith", Phone="555-0192" | Common name match; email domain is personal Gmail, not linked to CRM record |
| NEG-004 | Loyalty vs POS | LOYALTY_NUM=`000042` (after leading-zero restore) | POS_CUST_ID=42 (entirely different namespace) | Leading-zero defect makes loyalty code look like POS ID numerically |

---

## Duplicate Pairs at Varying Similarity (Required for WS-4 Eval)

| Pair ID | Similarity Level | Description |
|---------|-----------------|-------------|
| DUP-001 | Exact key match | Same CustomerID in POS and Merger A — confirmed same person via email |
| DUP-002 | Near-exact (name spelling variant) | "Katherine Moore" (POS) vs "Kathryn Moore" (CRM) — same address, same phone |
| DUP-003 | Plausible-but-different | Same address, different person — adult child still at parents' address |
