"""
WS-1: Generate realistic test data from AdventureWorks mappings.
Creates CSV fixtures per source system with documented native noise + injected defects.

Run: python scripts/generate_test_data.py
Output: data/fixtures/<source_system>.csv
"""

import csv
import os
import random
import unicodedata
from pathlib import Path

OUTPUT_DIR = Path("data/fixtures")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)


def inject_timezone_stripped_timestamp(ts: str) -> str:
    """INJ-POS-001: Remove timezone info from timestamp."""
    return ts.replace("Z", "").replace("+00:00", "").split(".")[0]


def inject_mixed_case_email(email: str) -> str:
    """INJ-EC-001: Randomly capitalise parts of email."""
    if random.random() < 0.3:
        parts = email.split("@")
        return parts[0].title() + "@" + parts[1].upper()
    return email


def inject_plus_address(email: str) -> str:
    """INJ-EC-002: Add RFC 5321 plus address."""
    if random.random() < 0.15:
        parts = email.split("@")
        return f"{parts[0]}+loyalty@{parts[1]}"
    return email


def inject_utf8_latin1_collision(name: str) -> str:
    """INJ-CRM-001: Simulate Latin-1 bytes misread as UTF-8."""
    mapping = {"ü": "MÃ¼", "ö": "MÃ¶", "ä": "MÃ¤", "é": "MÃ©", "ñ": "MÃ±"}
    for char, garbled in mapping.items():
        name = name.replace(char, garbled)
    return name


def inject_loyalty_leading_zero_drop(code: str) -> str:
    """INJ-LOY-001: Strip leading zeros (Excel auto-numeric)."""
    return str(int(code)) if code.isdigit() else code


# ── POS source ────────────────────────────────────────────────────────────────

POS_RECORDS = [
    {"customer_id": "1001", "first_name": "Katherine", "last_name": "Moore",
     "email": "kmoore@gmail.com", "phone": "303-555-0147",
     "address": "47 Birch Lane, Denver CO 80201",
     "order_date": inject_timezone_stripped_timestamp("2024-03-15T14:32:17Z"),
     "total_amount": "142.50"},
    {"customer_id": "5432", "first_name": "James", "last_name": "Wilson",
     "email": "jwilson78@email.com", "phone": "512-555-0099",
     "address": "8 Cedar Ave, Austin TX",
     "order_date": inject_timezone_stripped_timestamp("2024-01-20T09:15:00Z"),
     "total_amount": "89.99"},
    {"customer_id": "8901", "first_name": "Susan", "last_name": "Clark",
     "email": "sclark@example.com", "phone": "503-555-0123",
     "address": "123 Oak St, Portland OR",
     "order_date": inject_timezone_stripped_timestamp("2024-02-10T16:45:00Z"),
     "total_amount": "215.00"},
    {"customer_id": "2200", "first_name": "Robert", "last_name": "Smith",
     "email": "rsmith@outlook.com", "phone": "207-555-0188",
     "address": "12 Elm St, Portland OR",
     "order_date": inject_timezone_stripped_timestamp("2024-04-05T11:00:00Z"),
     "total_amount": "330.75"},
]


def write_pos_fixture():
    out = OUTPUT_DIR / "pos.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(POS_RECORDS[0].keys()))
        writer.writeheader()
        writer.writerows(POS_RECORDS)
    print(f"Written: {out} ({len(POS_RECORDS)} rows)")


# ── E-Commerce source ─────────────────────────────────────────────────────────

EC_RECORDS = [
    {"email_address_id": "EC-8823", "business_entity_id": "8823",
     "email": inject_mixed_case_email("kmoore@gmail.com"),
     "modified_date": "2024-03-15"},
    {"email_address_id": "EC-9910", "business_entity_id": "9910",
     "email": inject_plus_address("rsmith@outlook.com"),
     "modified_date": "2024-04-05"},
    {"email_address_id": "EC-1100", "business_entity_id": "1100",
     "email": inject_mixed_case_email("alice.jones@contoso.com"),
     "modified_date": "2024-01-30"},
]


def write_ecommerce_fixture():
    out = OUTPUT_DIR / "ecommerce.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(EC_RECORDS[0].keys()))
        writer.writeheader()
        writer.writerows(EC_RECORDS)
    print(f"Written: {out} ({len(EC_RECORDS)} rows)")


# ── CRM source ────────────────────────────────────────────────────────────────

CRM_RECORDS = [
    {"business_entity_id": "8823", "first_name": "Kathryn",
     "last_name": inject_utf8_latin1_collision("Moore"),
     "phone": "303-555-0147", "address_line1": "47 Birch Ln",
     "city": "Denver", "state": "CO", "postal_code": "80201"},
    {"business_entity_id": "8901", "first_name": "Susan",
     "last_name": "Clark",
     "phone": "503-555-0123", "address_line1": "123 Oak St",
     "city": "Portland", "state": "ME", "postal_code": "04101"},  # Portland ME — negative case!
    {"business_entity_id": "5432", "first_name": "James",
     "last_name": "Wilson",
     "phone": "512-555-0055", "address_line1": "8 Cedar Ave",
     "city": "Austin", "state": "TX", "postal_code": "78701",
     "dob": "1965-11-03"},  # DOB differs from POS record — negative case
]


def write_crm_fixture():
    out = OUTPUT_DIR / "crm.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(CRM_RECORDS[0].keys()))
        writer.writeheader()
        writer.writerows(CRM_RECORDS)
    print(f"Written: {out} ({len(CRM_RECORDS)} rows)")


# ── Loyalty source ────────────────────────────────────────────────────────────

LOYALTY_RECORDS = [
    {"loyalty_num": inject_loyalty_leading_zero_drop("000042"), "store_name": "Fabrikam Denver",
     "business_type": "Specialty", "annual_revenue": "1200000"},
    {"loyalty_num": "000100", "store_name": "Fabrikam Seattle",
     "business_type": "Warehouse", "annual_revenue": ""},  # sparse demographics
    {"loyalty_num": inject_loyalty_leading_zero_drop("000007"), "store_name": "Fabrikam Portland",
     "business_type": "Value", "annual_revenue": "850000"},
]


def write_loyalty_fixture():
    out = OUTPUT_DIR / "loyalty.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(LOYALTY_RECORDS[0].keys()))
        writer.writeheader()
        writer.writerows(LOYALTY_RECORDS)
    print(f"Written: {out} ({len(LOYALTY_RECORDS)} rows)")


# ── Merger Source A ───────────────────────────────────────────────────────────

MERGER_A_RECORDS = [
    {"account_id": "5432", "name": "James Wilson", "dob": "1978-04-12",  # namespace collision!
     "address": "8 Cedar Ave, Austin TX", "phone": "512-555-0099",
     "created_date": "2021-06-01"},
    {"account_id": "1001", "name": "Katherine Moore",
     "address": "47 Birch Lane, Denver CO", "phone": "303-555-0147",
     "created_date": "2021-08-15"},
]


def write_merger_a_fixture():
    out = OUTPUT_DIR / "merger_a.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(MERGER_A_RECORDS[0].keys()))
        writer.writeheader()
        writer.writerows(MERGER_A_RECORDS)
    print(f"Written: {out} ({len(MERGER_A_RECORDS)} rows)")


# ── Merger Source C ───────────────────────────────────────────────────────────

import uuid as _uuid

MERGER_C_RECORDS = [
    {"uuid": str(_uuid.uuid4()), "first_name": "Alice", "last_name": "Jones",
     "email": "alice.jones@contoso.com", "phone": None,  # 40% null phone
     "address_line1": "500 Pine St", "city": "Seattle", "state": "WA",
     "created_date": "2023-11-01"},
    {"uuid": str(_uuid.uuid4()), "first_name": "Robert", "last_name": "Smith",
     "email": "rsmith@outlook.com", "phone": "207-555-0188",
     "address_line1": None, "city": "Portland", "state": "OR",  # 18% null address
     "created_date": "2023-12-10"},
]


def write_merger_c_fixture():
    out = OUTPUT_DIR / "merger_c.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(MERGER_C_RECORDS[0].keys()))
        writer.writeheader()
        writer.writerows(MERGER_C_RECORDS)
    print(f"Written: {out} ({len(MERGER_C_RECORDS)} rows)")


if __name__ == "__main__":
    write_pos_fixture()
    write_ecommerce_fixture()
    write_crm_fixture()
    write_loyalty_fixture()
    write_merger_a_fixture()
    write_merger_c_fixture()
    print("\nAll test fixtures written to data/fixtures/")
    print("Native AW noise documented in data/defect_inventory.md")
