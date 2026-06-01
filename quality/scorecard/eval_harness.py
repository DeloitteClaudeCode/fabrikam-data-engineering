"""
WS-7: Entity matcher evaluation harness.
Runs on every PR touching the matcher. Fails CI if false-confidence rate increases > 1pp vs main.

Metrics: precision, recall, F1, false-confidence rate.
Dataset: stratified labeled pairs (match / non-match / unclear) from golden_pairs.py.
"""

import json
import logging
import os
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

from .golden_pairs import load_golden_pairs, Pair, Label
from silver.entity_resolution.matcher import match_records, MatchResult

logger = logging.getLogger(__name__)

HIGH_CONFIDENCE_THRESHOLD = 0.85
CI_FALSE_CONFIDENCE_REGRESSION_THRESHOLD = 0.01  # 1pp increase blocks merge


@dataclass
class EvalMetrics:
    precision: float
    recall: float
    f1: float
    false_confidence_rate: float
    total_pairs: int
    stratum_breakdown: dict[str, dict]

    def passes_acceptance_criteria(self) -> bool:
        return (
            self.precision >= 0.92
            and self.recall >= 0.85
            and self.false_confidence_rate <= 0.05
        )

    def report(self) -> str:
        lines = [
            f"Entity Matcher Scorecard",
            f"  Precision:            {self.precision:.3f}  (target ≥0.92)",
            f"  Recall:               {self.recall:.3f}  (target ≥0.85)",
            f"  F1:                   {self.f1:.3f}",
            f"  False-confidence rate:{self.false_confidence_rate:.3f}  (target ≤0.05)",
            f"  Total pairs:          {self.total_pairs}",
            "",
            "Stratum Breakdown:",
        ]
        for stratum, stats in self.stratum_breakdown.items():
            lines.append(f"  {stratum}: precision={stats['precision']:.3f}, recall={stats['recall']:.3f}, n={stats['n']}")
        lines.append("")
        lines.append("PASS" if self.passes_acceptance_criteria() else "FAIL — acceptance criteria not met")
        return "\n".join(lines)


def run_evaluation(
    pairs: list[Pair] | None = None,
    client: anthropic.Anthropic | None = None,
    cache_results: bool = True,
) -> EvalMetrics:
    if pairs is None:
        pairs = load_golden_pairs()
    if client is None:
        client = anthropic.Anthropic()

    tp = fp = fn = tn = 0
    false_confidence_errors = 0
    high_confidence_predictions = 0
    stratum_stats: dict[str, dict] = {}

    results_cache = []

    for pair in pairs:
        if pair.label == Label.UNCLEAR:
            continue  # skip ambiguous pairs for precision/recall

        result: MatchResult = match_records(pair.record_a, pair.record_b, client)
        predicted_match = result.match
        actual_match = pair.label == Label.MATCH

        if result.confidence >= HIGH_CONFIDENCE_THRESHOLD:
            high_confidence_predictions += 1
            if predicted_match != actual_match:
                false_confidence_errors += 1

        if predicted_match and actual_match:
            tp += 1
        elif predicted_match and not actual_match:
            fp += 1
        elif not predicted_match and actual_match:
            fn += 1
        else:
            tn += 1

        # Stratum tracking
        stratum = pair.stratum
        if stratum not in stratum_stats:
            stratum_stats[stratum] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "n": 0}
        s = stratum_stats[stratum]
        s["n"] += 1
        if predicted_match and actual_match: s["tp"] += 1
        elif predicted_match and not actual_match: s["fp"] += 1
        elif not predicted_match and actual_match: s["fn"] += 1
        else: s["tn"] += 1

        results_cache.append({
            "pair_id": pair.pair_id,
            "label": pair.label.value,
            "predicted_match": predicted_match,
            "confidence": result.confidence,
            "reason": result.reason,
            "stratum": stratum,
        })

    if cache_results:
        cache_path = Path("quality/scorecard/last_run.jsonl")
        with cache_path.open("w") as f:
            for r in results_cache:
                f.write(json.dumps(r) + "\n")

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    false_confidence_rate = (
        false_confidence_errors / high_confidence_predictions
        if high_confidence_predictions > 0 else 0.0
    )

    stratum_breakdown = {}
    for stratum, s in stratum_stats.items():
        p = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) > 0 else 0.0
        r = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) > 0 else 0.0
        stratum_breakdown[stratum] = {"precision": p, "recall": r, "n": s["n"]}

    return EvalMetrics(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        false_confidence_rate=round(false_confidence_rate, 4),
        total_pairs=tp + fp + fn + tn,
        stratum_breakdown=stratum_breakdown,
    )


def check_regression(current: EvalMetrics, baseline_path: str = "quality/scorecard/baseline.json") -> bool:
    """Returns True if current metrics pass (no regression). False = CI BREAK."""
    baseline_file = Path(baseline_path)
    if not baseline_file.exists():
        logger.info("No baseline found — writing current as baseline")
        with baseline_file.open("w") as f:
            json.dump({"false_confidence_rate": current.false_confidence_rate}, f)
        return True

    baseline = json.loads(baseline_file.read_text())
    baseline_fcr = baseline.get("false_confidence_rate", 0.0)
    regression = current.false_confidence_rate - baseline_fcr
    if regression > CI_FALSE_CONFIDENCE_REGRESSION_THRESHOLD:
        logger.error(
            "CI BREAK: false-confidence rate increased by %.3f (%.3f → %.3f). Merge blocked.",
            regression, baseline_fcr, current.false_confidence_rate,
        )
        return False
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    metrics = run_evaluation()
    print(metrics.report())
    passed = check_regression(metrics)
    import sys
    sys.exit(0 if passed and metrics.passes_acceptance_criteria() else 1)
