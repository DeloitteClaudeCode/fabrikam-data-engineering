# Silver Zone — CLAUDE.md

## Zone Contract: CONFORMED

**Mutation Policy:** Insert or full overwrite on reprocess. No partial updates.  
**Retention:** 3 years.  
**PII:** Pseudonymised at write time. No raw PII in Silver output tables.  
**Who Reads:** Data engineers, ML engineers.

## Entity Resolution Rules
- Every golden customer record must carry field-level confidence scores (0.0–1.0).
- Every merge decision traces to a named survivorship rule (see `silver/entity_resolution/survivorship.py`).
- The entity matcher prompt MUST include at least 2 positive examples and 1 negative example (records that look similar but are provably different people).
- Confidence < 0.5 → route to manual review queue, do NOT merge.

## Survivorship Precedence (Customer Fields)
```
email:          ecommerce > crm > pos (most structured source wins)
phone:          crm > pos > loyalty (most complete wins)
address:        crm > merger_c > pos (most recently acquired wins)
loyalty_num:    loyalty (canonical — only source)
name:           crm > pos (UTF-8 normalised before comparison)
```

## Rules
- Pseudonymise PII columns using reversible keyed hash (store key in secrets manager, not in code).
- Log the survivorship rule name that resolved each conflicted field.
- Reprocessing from Bronze is always safe — Silver is fully derived.
