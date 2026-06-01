"""
WS-4: Entity matcher — Claude-assisted matching with deterministic survivorship.

Few-shot prompt includes:
  - 2 positive examples (records that ARE the same person)
  - 1 negative example (records that LOOK similar but are provably different people)

Confidence < 0.5 → manual review queue, NOT merged.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import anthropic

from .survivorship import merge_customer_record
from .confidence import score_golden_record

logger = logging.getLogger(__name__)

MATCHER_PROMPT = """You are a customer entity resolution expert for Fabrikam Retail.
Your task: decide if two customer records refer to the SAME physical person.

Rules:
- Respond ONLY with valid JSON: {"match": true/false, "confidence": 0.0-1.0, "reason": "..."}
- confidence must reflect genuine certainty, NOT optimism. If unsure, use 0.3-0.6.
- A high-confidence (>0.85) prediction that is wrong is far worse than a low-confidence correct one.

--- POSITIVE EXAMPLE 1 (same person) ---
Record A: {{"customer_id": "POS-8823", "name": "Katherine Moore", "email": "kmoore@gmail.com", "address": "47 Birch Lane, Denver CO 80201", "phone": "303-555-0147"}}
Record B: {{"business_entity_id": "CRM-8823", "name": "Kathryn Moore", "email": "kmoore@gmail.com", "address": "47 Birch Ln, Denver CO 80201", "phone": "303-555-0147"}}
Answer: {{"match": true, "confidence": 0.97, "reason": "Identical email and phone. Name is a spelling variant (Katherine/Kathryn) — common nickname pair. Address is abbreviated but same street+zip."}}

--- POSITIVE EXAMPLE 2 (same person, trickier) ---
Record A: {{"loyalty_num": "000042", "name": "Robert J. Smith", "email": "rsmith@outlook.com", "address": "12 Elm St, Portland OR"}}
Record B: {{"customer_id": "EC-9910", "name": "Bob Smith", "email": "rsmith@outlook.com", "address": "12 Elm Street, Portland OR 97201"}}
Answer: {{"match": true, "confidence": 0.93, "reason": "Identical email. 'Bob' is a standard nickname for 'Robert'. Address matches with abbreviation difference. Loyalty_num=000042 != customer_id=9910 but these are different key namespaces."}}

--- NEGATIVE EXAMPLE (NOT the same person — do NOT merge) ---
Record A: {{"customer_id": "POS-5432", "name": "James Wilson", "dob": "1978-04-12", "address": "8 Cedar Ave, Austin TX"}}
Record B: {{"account_id": "MA-5432", "name": "James Wilson", "dob": "1965-11-03", "address": "8 Cedar Ave, Austin TX"}}
Answer: {{"match": false, "confidence": 0.91, "reason": "CRITICAL: Same key value (5432) but this is a known namespace collision between POS and Merger Source A — these are different integer sequences. DOB differs by 13 years. Same name + address likely means two James Wilsons at the same address (e.g. father and son). Do NOT merge."}}

--- YOUR TASK ---
Record A: {record_a}
Record B: {record_b}

Answer:"""


@dataclass
class MatchResult:
    match: bool
    confidence: float
    reason: str
    record_a_id: str
    record_b_id: str


def match_records(
    record_a: dict,
    record_b: dict,
    client: anthropic.Anthropic | None = None,
) -> MatchResult:
    """
    Use Claude to determine if two records refer to the same person.
    Returns structured MatchResult with confidence score and reasoning.
    """
    if client is None:
        client = anthropic.Anthropic()

    prompt = MATCHER_PROMPT.replace("{record_a}", json.dumps(record_a, ensure_ascii=False)).replace("{record_b}", json.dumps(record_b, ensure_ascii=False))

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Extract JSON from response
    start = raw.find("{")
    end = raw.rfind("}") + 1
    result_json = json.loads(raw[start:end])

    return MatchResult(
        match=result_json["match"],
        confidence=float(result_json["confidence"]),
        reason=result_json.get("reason", ""),
        record_a_id=str(record_a.get("customer_id") or record_a.get("business_entity_id") or "unknown"),
        record_b_id=str(record_b.get("customer_id") or record_b.get("account_id") or "unknown"),
    )


def resolve_customer_cluster(
    cluster: list[dict],
    source_labels: list[str],
    client: anthropic.Anthropic | None = None,
) -> dict[str, Any] | None:
    """
    Given a cluster of candidate-matching records, resolve to a single golden record.
    Records with match confidence < 0.5 are routed to manual review (returned as None).
    """
    if len(cluster) == 1:
        return cluster[0]

    # Pairwise matching: use first record as anchor
    anchor = cluster[0]
    anchor_source = source_labels[0] if source_labels else "unknown"

    per_source_fields = {anchor_source: anchor}

    for i, record in enumerate(cluster[1:], 1):
        src = source_labels[i] if i < len(source_labels) else f"source_{i}"
        result = match_records(anchor, record, client)

        if result.confidence < 0.5:
            logger.warning(
                "Low-confidence match (%.2f) between %s and %s — routing to manual review",
                result.confidence, result.record_a_id, result.record_b_id,
            )
            return None  # manual review

        if result.match:
            per_source_fields[src] = record
            logger.info("Match confirmed (%.2f): %s", result.confidence, result.reason)
        else:
            logger.info("Non-match (%.2f): %s", result.confidence, result.reason)

    golden_fields = merge_customer_record(per_source_fields)
    scores = score_golden_record(golden_fields)

    golden_record = {
        field: sv.value for field, sv in golden_fields.items()
    }
    golden_record["_confidence"] = scores.record_score
    golden_record["_field_confidence"] = scores.field_scores
    golden_record["_survivorship_rules"] = {
        field: sv.rule_name for field, sv in golden_fields.items()
    }
    golden_record["_source_systems"] = list(per_source_fields.keys())
    golden_record["_high_confidence"] = scores.high_confidence
    golden_record["_low_confidence_fields"] = scores.low_confidence_fields

    return golden_record
