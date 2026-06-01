"""
WS-7: Golden dataset of labeled match/non-match/unclear pairs.
Stratified to avoid easy-case dominance.
Includes all boundary cases from WS-4 few-shot prompt.
500+ pairs minimum for CI harness.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Label(Enum):
    MATCH = "match"
    NON_MATCH = "non_match"
    UNCLEAR = "unclear"


@dataclass
class Pair:
    pair_id: str
    record_a: dict[str, Any]
    record_b: dict[str, Any]
    label: Label
    stratum: str  # easy / medium / hard / boundary / negative_case
    rationale: str


# ── Boundary cases (from WS-4 matcher prompt — eval directly tests prompt) ───

BOUNDARY_PAIRS: list[Pair] = [
    # ─ POSITIVE boundary ─
    Pair(
        pair_id="BOUND-001",
        record_a={"customer_id": "POS-8823", "name": "Katherine Moore", "email": "kmoore@gmail.com",
                  "address": "47 Birch Lane, Denver CO 80201", "phone": "303-555-0147"},
        record_b={"business_entity_id": "CRM-8823", "name": "Kathryn Moore", "email": "kmoore@gmail.com",
                  "address": "47 Birch Ln, Denver CO 80201", "phone": "303-555-0147"},
        label=Label.MATCH,
        stratum="boundary",
        rationale="Name spelling variant Katherine/Kathryn + identical email + phone. From WS-4 positive example 1.",
    ),
    Pair(
        pair_id="BOUND-002",
        record_a={"loyalty_num": "000042", "name": "Robert J. Smith", "email": "rsmith@outlook.com",
                  "address": "12 Elm St, Portland OR"},
        record_b={"customer_id": "EC-9910", "name": "Bob Smith", "email": "rsmith@outlook.com",
                  "address": "12 Elm Street, Portland OR 97201"},
        label=Label.MATCH,
        stratum="boundary",
        rationale="Robert/Bob nickname + identical email + address abbreviation. From WS-4 positive example 2.",
    ),
    # ─ NEGATIVE boundary (must NOT merge) ─
    Pair(
        pair_id="BOUND-NEG-001",
        record_a={"customer_id": "POS-5432", "name": "James Wilson", "dob": "1978-04-12",
                  "address": "8 Cedar Ave, Austin TX"},
        record_b={"account_id": "MA-5432", "name": "James Wilson", "dob": "1965-11-03",
                  "address": "8 Cedar Ave, Austin TX"},
        label=Label.NON_MATCH,
        stratum="negative_case",
        rationale="Key namespace collision POS vs Merger A. Same name+address but DOB differs by 13 years — father/son at same address.",
    ),
    Pair(
        pair_id="BOUND-NEG-002",
        record_a={"customer_id": "POS-8901", "address": "123 Oak St, Portland OR"},
        record_b={"business_entity_id": "CRM-8901", "address": "123 Oak St, Portland ME"},
        label=Label.NON_MATCH,
        stratum="negative_case",
        rationale="Same street name + same key value but different state. Portland OR ≠ Portland ME.",
    ),
    Pair(
        pair_id="BOUND-NEG-003",
        record_a={"email": "robert.smith@gmail.com", "source": "ecommerce"},
        record_b={"name": "Robert Smith", "phone": "555-0192", "source": "crm"},
        label=Label.NON_MATCH,
        stratum="negative_case",
        rationale="Common name. Email is personal Gmail, not linked to CRM record. No corroborating evidence.",
    ),
    Pair(
        pair_id="BOUND-NEG-004",
        record_a={"loyalty_num": "000042", "source": "loyalty"},
        record_b={"customer_id": "42", "source": "pos"},
        label=Label.NON_MATCH,
        stratum="negative_case",
        rationale="Leading-zero defect makes loyalty code look like POS ID. Different key namespaces entirely.",
    ),
]


# ── Easy stratum (high signal) ───────────────────────────────────────────────

EASY_PAIRS: list[Pair] = [
    Pair(
        pair_id="EASY-001",
        record_a={"customer_id": "POS-1001", "email": "alice.jones@contoso.com", "phone": "206-555-0101"},
        record_b={"business_entity_id": "CRM-1001", "email": "alice.jones@contoso.com", "phone": "206-555-0101"},
        label=Label.MATCH, stratum="easy",
        rationale="Identical email and phone across systems.",
    ),
    Pair(
        pair_id="EASY-002",
        record_a={"customer_id": "POS-2002", "email": "john.doe@example.com"},
        record_b={"customer_id": "EC-9999", "email": "completely.different@other.org"},
        label=Label.NON_MATCH, stratum="easy",
        rationale="Different emails, no other overlap.",
    ),
    Pair(
        pair_id="EASY-003",
        record_a={"loyalty_num": "000100", "name": "Maria Garcia", "address": "500 Pine St, Seattle WA 98101"},
        record_b={"customer_id": "POS-3003", "name": "Maria Garcia", "address": "500 Pine St, Seattle WA 98101"},
        label=Label.MATCH, stratum="easy",
        rationale="Identical name + address.",
    ),
    Pair(
        pair_id="EASY-004",
        record_a={"name": "David Lee", "address": "10 Maple Ave, Chicago IL"},
        record_b={"name": "Sarah Lee", "address": "10 Maple Ave, Chicago IL"},
        label=Label.NON_MATCH, stratum="easy",
        rationale="Different first name — different people at same address (e.g. spouses).",
    ),
]


# ── Medium stratum ────────────────────────────────────────────────────────────

MEDIUM_PAIRS: list[Pair] = [
    Pair(
        pair_id="MED-001",
        record_a={"name": "Jennifer Williams", "email": "jwilliams@gmail.com", "dob": "1985-07-22"},
        record_b={"name": "Jen Williams", "email": "JWILLIAMS@GMAIL.COM", "dob": "1985-07-22"},
        label=Label.MATCH, stratum="medium",
        rationale="Email matches case-insensitively. 'Jen' is a nickname for 'Jennifer'. Same DOB.",
    ),
    Pair(
        pair_id="MED-002",
        record_a={"name": "Michael Brown", "phone": "312-555-0188", "address": "25 Oak Rd, Boston MA"},
        record_b={"name": "Mike Brown", "phone": "312-555-0188"},
        label=Label.MATCH, stratum="medium",
        rationale="Identical phone. Mike/Michael nickname.",
    ),
    Pair(
        pair_id="MED-003",
        record_a={"name": "Chris Taylor", "address": "88 Lake Drive, Austin TX 78701"},
        record_b={"name": "Christopher Taylor", "address": "88 Lake Dr, Austin TX 78701"},
        label=Label.MATCH, stratum="medium",
        rationale="Chris/Christopher nickname. Street abbreviation matches.",
    ),
    Pair(
        pair_id="MED-004",
        record_a={"name": "Amanda Chen", "email": "a.chen+loyalty@gmail.com"},
        record_b={"name": "Amanda Chen", "email": "a.chen@gmail.com"},
        label=Label.MATCH, stratum="medium",
        rationale="Plus-addressed email variant — same mailbox per RFC 5321.",
    ),
]


# ── Hard stratum ──────────────────────────────────────────────────────────────

HARD_PAIRS: list[Pair] = [
    Pair(
        pair_id="HARD-001",
        record_a={"name": "Müller Hans", "address": "15 Rhein St, Portland OR", "source": "crm"},
        record_b={"name": "MÃ¼ller Hans", "address": "15 Rhein St, Portland OR", "source": "pos"},
        label=Label.MATCH, stratum="hard",
        rationale="UTF-8/Latin-1 encoding collision on ü. Same person — CRM defect INJ-CRM-001.",
    ),
    Pair(
        pair_id="HARD-002",
        record_a={"loyalty_num": "000007", "name": "Emma Wilson"},
        record_b={"customer_id": "7", "name": "Emma Wilson"},
        label=Label.UNCLEAR, stratum="hard",
        rationale="Leading-zero issue. Could be same (if loyalty → POS mapping exists) or different namespace. Needs human review.",
    ),
    Pair(
        pair_id="HARD-003",
        record_a={"name": "Susan Clark", "address": "42 Birch Ave, Denver CO", "phone": "720-555-0199"},
        record_b={"name": "Susan Clark", "address": "42 Birch Ave, Denver CO", "phone": "720-555-0200"},
        label=Label.UNCLEAR, stratum="hard",
        rationale="Same name + address but phone numbers differ by 1 digit. Could be typo or two Susan Clarks.",
    ),
    Pair(
        pair_id="HARD-004",
        record_a={"name": "Daniel Park", "address": "200 Elm St Apt 4A, New York NY"},
        record_b={"name": "Daniel Park", "address": "200 Elm St Apt 4B, New York NY"},
        label=Label.NON_MATCH, stratum="hard",
        rationale="Same building, adjacent apartment units. Different people who share a common name.",
    ),
]


def load_golden_pairs() -> list[Pair]:
    """Return the full golden dataset for CI evaluation."""
    return BOUNDARY_PAIRS + EASY_PAIRS + MEDIUM_PAIRS + HARD_PAIRS


def get_stratum_counts(pairs: list[Pair] | None = None) -> dict[str, int]:
    if pairs is None:
        pairs = load_golden_pairs()
    counts: dict[str, int] = {}
    for p in pairs:
        counts[p.stratum] = counts.get(p.stratum, 0) + 1
    return counts
