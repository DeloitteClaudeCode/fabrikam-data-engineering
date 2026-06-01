"""
WS-4: Confidence scoring for golden customer records.
Field-level (0.0–1.0) and record-level aggregate scores.
"""

from dataclasses import dataclass
from typing import Any

from .survivorship import SurvivedField


# Key fields that anchor record confidence
KEY_FIELDS = {"email", "phone", "loyalty_num", "first_name", "last_name", "address"}
KEY_FIELD_WEIGHT = 2.0
STANDARD_FIELD_WEIGHT = 1.0


@dataclass
class ConfidenceReport:
    field_scores: dict[str, float]
    record_score: float
    high_confidence: bool   # record_score >= 0.85
    low_confidence_fields: list[str]


def field_confidence(survived: SurvivedField) -> float:
    """Derive field-level confidence from survivorship outcome."""
    return survived.confidence


def record_confidence(field_scores: dict[str, float]) -> float:
    """Weighted average of field scores, with key fields weighted double."""
    total_weight = 0.0
    weighted_sum = 0.0
    for field, score in field_scores.items():
        w = KEY_FIELD_WEIGHT if field in KEY_FIELDS else STANDARD_FIELD_WEIGHT
        weighted_sum += score * w
        total_weight += w
    return round(weighted_sum / total_weight, 4) if total_weight > 0 else 0.0


def score_golden_record(golden: dict[str, SurvivedField]) -> ConfidenceReport:
    """Produce field-level and record-level confidence for a merged golden record."""
    field_scores = {f: field_confidence(sv) for f, sv in golden.items()}
    rec_score = record_confidence(field_scores)
    low = [f for f, s in field_scores.items() if s < 0.5]
    return ConfidenceReport(
        field_scores=field_scores,
        record_score=rec_score,
        high_confidence=rec_score >= 0.85,
        low_confidence_fields=low,
    )
