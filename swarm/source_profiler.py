"""
WS-9 (Stretch): Source profiling subagent — scores one source system.
One instance per source; seven run in parallel via the coordinator.

Each subagent receives ALL context explicitly in its prompt.
Subagents do NOT inherit coordinator state.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

PROFILER_PROMPT = """You are a data quality analyst profiling a single data source for Fabrikam Retail.

Source system: {source_system}
Records provided: {record_count} rows
Sample records (first 5):
{sample_records}

Known defects for this source:
{known_defects}

Score this source on EACH of the following dimensions (0-100):
1. completeness: What fraction of expected fields are populated?
2. freshness: How recent is the data? (100 = within last 24h, 0 = over 1 year old)
3. key_coverage: What fraction of records have a valid primary key?
4. anomaly_count: How many distinct anomaly types are present? (100 = 0 anomalies, 0 = 10+ distinct types)
5. pii_surface_area: How many PII-containing fields are exposed? (100 = 0 PII fields, 0 = 10+ fields)

Also provide:
- top_issues: list of top 3 specific data quality issues found
- recommended_action: one concrete next step for the data engineer

Respond ONLY with valid JSON matching this schema:
{{
  "source_system": "{source_system}",
  "scores": {{
    "completeness": <0-100>,
    "freshness": <0-100>,
    "key_coverage": <0-100>,
    "anomaly_count": <0-100>,
    "pii_surface_area": <0-100>
  }},
  "overall_health": <0-100 weighted average>,
  "top_issues": ["issue1", "issue2", "issue3"],
  "recommended_action": "..."
}}"""


@dataclass
class SourceProfile:
    source_system: str
    scores: dict[str, int]
    overall_health: int
    top_issues: list[str]
    recommended_action: str
    record_count: int
    raw_response: str


def profile_source(
    source_system: str,
    records: list[dict],
    known_defects: list[str],
    client: anthropic.Anthropic | None = None,
) -> SourceProfile:
    """
    Profile a single source system. ALL context passed explicitly — no shared state.
    Returns a SourceProfile with dimension scores and recommended action.
    """
    if client is None:
        client = anthropic.Anthropic()

    sample = records[:5]
    prompt = PROFILER_PROMPT.format(
        source_system=source_system,
        record_count=len(records),
        sample_records=json.dumps(sample, indent=2, ensure_ascii=False),
        known_defects=json.dumps(known_defects, indent=2),
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Fast model for parallel profiling
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    result = json.loads(raw[start:end])

    return SourceProfile(
        source_system=source_system,
        scores=result["scores"],
        overall_health=result["overall_health"],
        top_issues=result.get("top_issues", []),
        recommended_action=result.get("recommended_action", ""),
        record_count=len(records),
        raw_response=raw,
    )
