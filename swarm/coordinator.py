"""
WS-9 (Stretch): Coordinator subagent — runs 7 source profilers in parallel,
aggregates into a single swamp health dashboard.

All context passed explicitly to each subagent. Decomposition is legible.
Target: dashboard rendered in < 90 seconds for all 7 sources.
"""

import concurrent.futures
import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import anthropic

from .source_profiler import SourceProfile, profile_source

logger = logging.getLogger(__name__)

# Defect inventory — passed explicitly to each subagent
SOURCE_DEFECTS = {
    "pos":       ["INJ-POS-001: timezone-stripped timestamps", "INJ-POS-002: key namespace collision with merger_a"],
    "ecommerce": ["INJ-EC-001: mixed-case emails", "INJ-EC-002: RFC 5321 plus-address variants"],
    "crm":       ["INJ-CRM-001: UTF-8/Latin-1 encoding collision", "INJ-CRM-002: address schema mismatch"],
    "loyalty":   ["INJ-LOY-001: leading zeros dropped in CSV exports", "NATIVE-005: sparse demographics"],
    "merger_a":  ["INJ-MA-001: account_id namespace collision with POS", "NATIVE-003: overlapping key ranges"],
    "merger_b":  ["INJ-MB-001: free-form CUST_CODE, no format enforcement", "NATIVE-004: sparse MiddleName"],
    "merger_c":  ["INJ-MC-001: 40% null phone", "INJ-MC-002: 18% null address"],
}

DIMENSION_WEIGHTS = {
    "completeness":     0.25,
    "freshness":        0.20,
    "key_coverage":     0.25,
    "anomaly_count":    0.20,
    "pii_surface_area": 0.10,
}


@dataclass
class SwampHealthDashboard:
    overall_health_score: float
    source_profiles: list[SourceProfile]
    elapsed_seconds: float
    generated_at: str
    coordinator_context: dict[str, Any]  # explicit context for auditability


def _load_source_records(source_system: str, bronze_path: Path) -> list[dict]:
    """Load available Bronze records for a source. Falls back to empty list if not yet ingested."""
    records = []
    for f in bronze_path.glob(f"{source_system}*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def run_swarm(
    bronze_path: str | Path = "bronze/data",
    output_path: str | Path = "quality/swamp_health.json",
    client: anthropic.Anthropic | None = None,
    max_workers: int = 7,
) -> SwampHealthDashboard:
    """
    Launch 7 source-profiler subagents in parallel.
    Each receives explicit context — no shared state between subagents.
    Returns aggregated SwampHealthDashboard.
    """
    if client is None:
        client = anthropic.Anthropic()

    start = time.monotonic()
    bronze_path = Path(bronze_path)
    sources = list(SOURCE_DEFECTS.keys())

    # Build explicit context for each subagent (legible decomposition artifact)
    subagent_contexts = {}
    source_records = {}
    for source in sources:
        records = _load_source_records(source, bronze_path)
        source_records[source] = records
        subagent_contexts[source] = {
            "source_system": source,
            "record_count": len(records),
            "known_defects": SOURCE_DEFECTS[source],
            "sample_provided": records[:5],
        }

    logger.info("Launching %d profiler subagents in parallel...", len(sources))

    profiles: list[SourceProfile] = []
    errors: dict[str, str] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                profile_source,
                source,
                source_records[source],
                SOURCE_DEFECTS[source],
                client,
            ): source
            for source in sources
        }
        for future in concurrent.futures.as_completed(futures):
            source = futures[future]
            try:
                profile = future.result()
                profiles.append(profile)
                logger.info("Profiled %s: health=%d", source, profile.overall_health)
            except Exception as exc:
                errors[source] = str(exc)
                logger.error("Failed to profile %s: %s", source, exc)

    # Aggregate overall health (weighted average of source health scores)
    if profiles:
        overall = round(sum(p.overall_health for p in profiles) / len(profiles), 1)
    else:
        overall = 0.0

    elapsed = round(time.monotonic() - start, 2)
    from datetime import datetime, timezone
    dashboard = SwampHealthDashboard(
        overall_health_score=overall,
        source_profiles=profiles,
        elapsed_seconds=elapsed,
        generated_at=datetime.now(timezone.utc).isoformat(),
        coordinator_context={
            "subagent_prompts": subagent_contexts,  # full prompt context per subagent
            "errors": errors,
            "model_used": "claude-haiku-4-5-20251001",
            "parallelism": max_workers,
        },
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as f:
        json.dump(
            {
                "overall_health_score": dashboard.overall_health_score,
                "elapsed_seconds": dashboard.elapsed_seconds,
                "generated_at": dashboard.generated_at,
                "sources": [
                    {
                        "source_system": p.source_system,
                        "overall_health": p.overall_health,
                        "scores": p.scores,
                        "top_issues": p.top_issues,
                        "recommended_action": p.recommended_action,
                        "record_count": p.record_count,
                    }
                    for p in sorted(profiles, key=lambda p: p.overall_health)
                ],
                "errors": errors,
                "coordinator_context": subagent_contexts,  # legible decomposition
            },
            f, indent=2,
        )

    logger.info(
        "Swamp health dashboard complete in %.1fs. Overall: %.1f/100. Output: %s",
        elapsed, overall, output,
    )
    return dashboard


def print_dashboard(dashboard: SwampHealthDashboard):
    print(f"\n{'='*60}")
    print(f"FABRIKAM SWAMP HEALTH DASHBOARD")
    print(f"Overall Health: {dashboard.overall_health_score:.1f}/100")
    print(f"Generated: {dashboard.generated_at}  ({dashboard.elapsed_seconds}s)")
    print(f"{'='*60}")
    for p in sorted(dashboard.source_profiles, key=lambda x: x.overall_health):
        bar = "█" * (p.overall_health // 10) + "░" * (10 - p.overall_health // 10)
        print(f"\n{p.source_system:<12} [{bar}] {p.overall_health}/100")
        for issue in p.top_issues:
            print(f"  ⚠  {issue}")
        print(f"  → {p.recommended_action}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dashboard = run_swarm()
    print_dashboard(dashboard)
