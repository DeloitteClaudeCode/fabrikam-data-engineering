"""
WS-3: Flaky REST API ingestion with exponential backoff, circuit breaker, and dead-letter logging.
Simulates Merger Source C API (sparse, unreliable, UUID-keyed).
"""

import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .lineage import attach_lineage, make_lineage

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"        # normal — requests pass through
    OPEN = "open"            # tripped — requests blocked
    HALF_OPEN = "half_open"  # probe mode — one test request allowed


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    _failures: int = 0
    _state: CircuitState = CircuitState.CLOSED
    _opened_at: float = 0.0

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker: HALF_OPEN — probing")
            else:
                raise RuntimeError("Circuit breaker OPEN — requests blocked")

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise exc

    def _on_success(self):
        self._failures = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self):
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("Circuit breaker OPEN after %d failures", self._failures)


@dataclass
class ApiIngestionResult:
    records: list[dict] = field(default_factory=list)
    dead_letter: list[dict] = field(default_factory=list)
    total_attempts: int = 0
    circuit_trips: int = 0


def fetch_with_backoff(
    fetch_fn: Callable,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 32.0,
) -> Any:
    """Exponential backoff with jitter."""
    for attempt in range(max_retries):
        try:
            return fetch_fn()
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
            logger.warning("Attempt %d failed (%s). Retrying in %.1fs", attempt + 1, exc, delay)
            time.sleep(delay)


def ingest_from_api(
    endpoint: str,
    source_system: str,
    fetch_fn: Callable[[str], list[dict]],
    bronze_output_path: str | Path,
    circuit_breaker: CircuitBreaker | None = None,
    max_retries: int = 5,
) -> ApiIngestionResult:
    """
    Fetch records from a flaky REST API and land in Bronze.
    Uses exponential backoff + circuit breaker + dead-letter for permanent failures.
    """
    cb = circuit_breaker or CircuitBreaker()
    result = ApiIngestionResult()

    try:
        raw_records = fetch_with_backoff(
            lambda: cb.call(fetch_fn, endpoint),
            max_retries=max_retries,
        )
        result.total_attempts += 1
        result.records = raw_records or []
    except RuntimeError as exc:
        # Circuit breaker open
        result.circuit_trips += 1
        result.dead_letter.append({
            "endpoint": endpoint,
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "circuit_break",
        })
        logger.error("Dead-letter: circuit break for %s", endpoint)
        return result
    except Exception as exc:
        result.dead_letter.append({
            "endpoint": endpoint,
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "permanent_failure",
        })
        logger.error("Dead-letter: permanent failure for %s: %s", endpoint, exc)
        return result

    if result.records:
        columns = [(k, "string") for k in result.records[0].keys()]
        lineage = make_lineage(
            source_system=source_system,
            source_file=endpoint,
            row_count=len(result.records),
            columns=columns,
        )
        attach_lineage(result.records, lineage)

        output = Path(bronze_output_path)
        output.mkdir(parents=True, exist_ok=True)
        out_file = output / f"{source_system}_{lineage['run_id']}.jsonl"
        with out_file.open("w") as f:
            for r in result.records:
                f.write(json.dumps(r) + "\n")

    if result.dead_letter:
        output = Path(bronze_output_path)
        output.mkdir(parents=True, exist_ok=True)
        dl_file = output / f"{source_system}_dead_letter_{uuid.uuid4().hex[:8]}.jsonl"
        with dl_file.open("w") as f:
            for r in result.dead_letter:
                f.write(json.dumps(r) + "\n")

    logger.info(
        "API ingestion %s: %d records, %d dead-letter, %d circuit trips",
        source_system, len(result.records), len(result.dead_letter), result.circuit_trips,
    )
    return result
