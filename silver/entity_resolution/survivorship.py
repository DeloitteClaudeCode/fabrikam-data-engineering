"""
WS-4: Survivorship rules — explicit, coded field-by-field source precedence.
Every merge decision traces to a named rule. No anonymous merges.
"""

from dataclasses import dataclass
from typing import Any


SOURCE_PRECEDENCE = {
    # (field_name): [source_system in priority order, highest first]
    "email":        ["ecommerce", "crm", "pos"],
    "phone":        ["crm", "pos", "loyalty"],
    "address":      ["crm", "merger_c", "pos"],
    "first_name":   ["crm", "pos"],
    "last_name":    ["crm", "pos"],
    "loyalty_num":  ["loyalty"],       # canonical — only source
    "birth_date":   ["crm", "merger_c"],
}


@dataclass
class SurvivedField:
    value: Any
    source_system: str
    rule_name: str
    confidence: float


def apply_source_precedence(
    field: str,
    candidates: dict[str, Any],  # {source_system: value}
) -> SurvivedField:
    """
    RULE: source_precedence_{field}
    Pick the highest-precedence non-null value for a field.
    """
    precedence = SOURCE_PRECEDENCE.get(field, [])
    for source in precedence:
        val = candidates.get(source)
        if val is not None and str(val).strip() != "":
            return SurvivedField(
                value=val,
                source_system=source,
                rule_name=f"source_precedence_{field}",
                confidence=1.0 if source == precedence[0] else 0.8,
            )
    # Fallback: first non-null from any source
    for source, val in candidates.items():
        if val is not None and str(val).strip() != "":
            return SurvivedField(
                value=val,
                source_system=source,
                rule_name=f"fallback_first_nonnull_{field}",
                confidence=0.5,
            )
    return SurvivedField(value=None, source_system="none", rule_name=f"no_value_{field}", confidence=0.0)


def apply_most_recent(
    field: str,
    candidates: dict[str, tuple[Any, str]],  # {source: (value, updated_at_iso)}
) -> SurvivedField:
    """
    RULE: most_recent_{field}
    For fields where recency beats source preference (e.g. address after a move).
    """
    best_source, best_val, best_ts = None, None, ""
    for source, (val, updated_at) in candidates.items():
        if val and updated_at > best_ts:
            best_val, best_ts, best_source = val, updated_at, source
    return SurvivedField(
        value=best_val,
        source_system=best_source or "none",
        rule_name=f"most_recent_{field}",
        confidence=0.9 if best_val else 0.0,
    )


def apply_longest_populated(
    field: str,
    candidates: dict[str, Any],
) -> SurvivedField:
    """
    RULE: longest_populated_{field}
    For free-form fields (notes, middle_name) where completeness beats source.
    """
    best_source, best_val = None, None
    for source, val in candidates.items():
        if val and (best_val is None or len(str(val)) > len(str(best_val))):
            best_val, best_source = val, source
    return SurvivedField(
        value=best_val,
        source_system=best_source or "none",
        rule_name=f"longest_populated_{field}",
        confidence=0.7 if best_val else 0.0,
    )


def merge_customer_record(per_source_fields: dict[str, dict]) -> dict[str, SurvivedField]:
    """
    Merge fields from multiple source records into a single golden record.
    per_source_fields: {source_system: {field: value}}
    Returns: {field: SurvivedField}
    """
    fields = set()
    for source_fields in per_source_fields.values():
        fields.update(source_fields.keys())

    golden = {}
    for field in fields:
        candidates = {src: vals.get(field) for src, vals in per_source_fields.items()}
        if field in SOURCE_PRECEDENCE:
            golden[field] = apply_source_precedence(field, candidates)
        elif field in ("notes", "middle_name"):
            golden[field] = apply_longest_populated(field, candidates)
        else:
            golden[field] = apply_source_precedence(field, candidates)

    return golden
