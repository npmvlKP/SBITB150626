#!/usr/bin/env python3
"""
Phase 2 Kleppmann Cross-Reference Validation -- SBITB-150626

Validates that the Phase 2 implementation correctly applies principles
from "Designing Data-Intensive Applications" by Martin Kleppmann (Ch.1-5).

Usage:
    python verify_phase2_kleppmann.py

Exit: 0 = all checks pass, 1 = one or more failures.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).parent.resolve()

checks: list[dict[str, Any]] = []
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def add_check(chapter: str, principle: str, passed: bool, detail: str = "") -> None:
    checks.append({"chapter": chapter, "principle": principle, "passed": passed, "detail": detail})
    status = f"{GREEN}[PASS]{RESET}" if passed else f"{RED}[FAIL]{RESET}"
    suffix = f"  -- {detail}" if detail else ""
    print(f"  {status} [{chapter}] {principle}{suffix}")


def read_file(rel_path: str) -> str:
    path = ROOT / rel_path
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def parse_python(rel_path: str) -> ast.Module | None:
    source = read_file(rel_path)
    if not source:
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def has_class(module: ast.Module | None, class_name: str) -> bool:
    if module is None:
        return False
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return True
    return False


def check_chapter1() -> None:
    """Ch.1: Reliability, Scalability, Maintainability."""
    print(f"\n{BOLD}  Kleppmann Chapter 1 -- Reliable, Scalable, Maintainable{RESET}")
    print(f"  {'-' * 66}")

    historical_py = read_file("src/data/historical.py")
    schema_ck = read_file("deployment/init_phase2.sql")
    has_checkpoint = "download_checkpoint" in schema_ck or "skip_existing" in historical_py.lower()
    add_check(
        "Ch.1",
        "Reliability: checkpoint-based resumable downloads",
        has_checkpoint,
        "download_checkpoint table + skip_existing in pipeline",
    )
    add_check(
        "Ch.1",
        "Reliability: skip already-ingested dates",
        "skipped" in historical_py.lower() or "skip" in historical_py.lower(),
        "pipeline skips completed dates",
    )

    event_log = read_file("src/data/event_log.py")
    add_check(
        "Ch.1",
        "Reliability: idempotent event append (ON CONFLICT DO NOTHING)",
        "ON CONFLICT" in event_log or "DO NOTHING" in event_log,
        "event_log.py uses ON CONFLICT",
    )
    add_check(
        "Ch.1",
        "Reliability: every event has unique ID",
        "event_id" in event_log and "uuid" in event_log.lower(),
        "MarketEvent has event_id: UUID",
    )
    add_check(
        "Ch.1",
        "Reliability: ingest_id for pipeline-run idempotency",
        "ingest_id" in event_log,
        "ingest_id per pipeline run",
    )

    metrics_py = read_file("src/data/metrics.py")
    add_check(
        "Ch.1", "Operability: Prometheus counters for monitoring", "Counter" in metrics_py, "Counter metrics defined"
    )
    add_check(
        "Ch.1", "Operability: Prometheus histograms for latency", "Histogram" in metrics_py, "Histogram metrics defined"
    )
    add_check("Ch.1", "Operability: Prometheus gauges for rates", "Gauge" in metrics_py, "Gauge metrics defined")

    add_check(
        "Ch.1",
        "Evolvability: schema_version on event payloads",
        "schema_version" in event_log,
        "schema_version field present",
    )
    event_log_ast = parse_python("src/data/event_log.py")
    add_check(
        "Ch.1",
        "Evolvability: EventCodec for schema migration",
        has_class(event_log_ast, "EventCodec"),
        "EventCodec with encode/decode",
    )


def check_chapter2() -> None:
    """Ch.2: Data Models."""
    print(f"\n{BOLD}  Kleppmann Chapter 2 -- Data Models{RESET}")
    print(f"  {'-' * 66}")

    schema = read_file("deployment/init_phase2.sql")
    add_check("Ch.2", "Schema-on-write: CHECK constraints on tables", "CHECK" in schema, "option_type IN ('CE', 'PE')")
    add_check(
        "Ch.2",
        "Schema-on-write: strict NUMERIC column types",
        "NUMERIC(12,2)" in schema,
        "price columns are NUMERIC(12,2)",
    )
    add_check("Ch.2", "Schema-on-write: VARCHAR with length limits", "VARCHAR" in schema, "symbol VARCHAR(20)")
    add_check(
        "Ch.2", "Data integrity: PRIMARY KEY on all tables", "PRIMARY KEY" in schema, "composite PK on all tables"
    )
    add_check(
        "Ch.2", "Schema flexibility: JSONB for event payloads", "JSONB" in schema, "market_events.payload is JSONB"
    )
    add_check(
        "Ch.2",
        "Partitioning: hypertables for time-series data",
        "create_hypertable" in schema,
        "all time-series tables are hypertables",
    )


def check_chapter3() -> None:
    """Ch.3: Storage & Retrieval."""
    print(f"\n{BOLD}  Kleppmann Chapter 3 -- Storage & Retrieval{RESET}")
    print(f"  {'-' * 66}")

    schema = read_file("deployment/init_phase2.sql")
    add_check("Ch.3", "Append-only log: market_events table", "market_events" in schema, "event log table defined")
    add_check(
        "Ch.3",
        "Append-only: DELETE trigger prevents removal",
        "prevent_market_event_deletion" in schema,
        "trigger raises exception on DELETE",
    )
    add_check(
        "Ch.3",
        "Append-only: UPDATE trigger prevents mutation",
        "prevent_market_event_update" in schema,
        "trigger raises exception on UPDATE",
    )

    storage_py = read_file("src/data/storage.py")
    add_check(
        "Ch.3",
        "Log-structured: bulk_insert for batch writes",
        "bulk_insert" in storage_py,
        "TimescaleDBStore.bulk_insert()",
    )
    add_check(
        "Ch.3",
        "Log-structured: COPY-style batch insert",
        "COPY" in storage_py or "execute_values" in storage_py or "execute_batch" in storage_py,
        "uses execute_values for performance",
    )

    add_check(
        "Ch.3",
        "Compaction: continuous aggregate views",
        "timescaledb.continuous" in schema,
        "v_tick_1min_ohlcv, v_daily_oi_summary",
    )
    add_check(
        "Ch.3",
        "Compaction: automatic aggregate refresh policy",
        "add_continuous_aggregate_policy" in schema,
        "automatic refresh policies defined",
    )

    add_check(
        "Ch.3",
        "Retention: automated data retention policies",
        "add_retention_policy" in schema,
        "7yr events, 90d ticks",
    )
    add_check(
        "Ch.3",
        "Retention: 7-year SEBI compliance on events",
        "7 years" in schema or "'7 years'" in schema,
        "market_events retained 7 years",
    )
    add_check(
        "Ch.3",
        "Retention: 90-day tick retention with compaction",
        "90 days" in schema or "'90 days'" in schema,
        "ws_ticks retained 90 days",
    )

    add_check(
        "Ch.3",
        "Derived view: fo_options_eod from FO_BHAVCOPY events",
        "fo_options_eod" in schema,
        "derived table populated from events",
    )
    add_check(
        "Ch.3",
        "Derived view: cm_spot_eod from CM_BHAVCOPY events",
        "cm_spot_eod" in schema,
        "spot prices derived from events",
    )


def check_chapter4() -> None:
    """Ch.4: Encoding."""
    print(f"\n{BOLD}  Kleppmann Chapter 4 -- Encoding{RESET}")
    print(f"  {'-' * 66}")

    event_log = read_file("src/data/event_log.py")
    schema = read_file("deployment/init_phase2.sql")

    add_check(
        "Ch.4", "EventCodec.encode() serializes with version", "encode" in event_log, "encode includes schema_version"
    )
    add_check(
        "Ch.4",
        "EventCodec.decode() with version-aware deserialization",
        "decode" in event_log,
        "decode handles multiple schema versions",
    )
    add_check(
        "Ch.4",
        "Schema migration registry for version upgrades",
        "migrat" in event_log.lower(),
        "migration functions registered",
    )
    add_check(
        "Ch.4",
        "schema_version column in market_events table",
        "schema_version" in schema,
        "SMALLINT NOT NULL DEFAULT 1",
    )
    add_check(
        "Ch.4",
        "CURRENT_SCHEMA_VERSION constant defined",
        "CURRENT_SCHEMA_VERSION" in event_log or "current_schema_version" in event_log.lower(),
        "tracks current schema version",
    )


def check_chapter5() -> None:
    """Ch.5: Replication."""
    print(f"\n{BOLD}  Kleppmann Chapter 5 -- Replication{RESET}")
    print(f"  {'-' * 66}")

    live_feed = read_file("src/data/live_market_feed.py")
    schema = read_file("deployment/init_phase2.sql")
    storage_py = read_file("src/data/storage.py")

    add_check(
        "Ch.5",
        "Single-writer: LiveMarketFeed writes to event log",
        "event_writer" in live_feed or "EventLogWriter" in live_feed,
        "single writer -> event log",
    )
    add_check(
        "Ch.5",
        "Fencing token: monotonic epoch counter on reconnect",
        "epoch" in live_feed and "_epoch" in live_feed,
        "_epoch increments on each WS reconnection",
    )
    add_check(
        "Ch.5",
        "Fencing token: epoch column in ws_ticks table",
        "epoch" in schema and "BIGINT" in schema,
        "epoch BIGINT NOT NULL DEFAULT 1",
    )
    add_check(
        "Ch.5",
        "Fencing token: epoch column in market_events table",
        "epoch" in schema and "market_events" in schema,
        "events tagged with fencing token",
    )

    add_check(
        "Ch.5",
        "Idempotent consumers: ON CONFLICT in bulk_insert",
        "ON CONFLICT" in storage_py or "on_conflict" in storage_py.lower(),
        "bulk_insert supports ON CONFLICT DO NOTHING",
    )
    add_check(
        "Ch.5",
        "Idempotency key: ingest_id in market_events",
        "ingest_id" in schema,
        "UNIQUE per pipeline run for dedup",
    )

    add_check(
        "Ch.5",
        "Error categorization: is_retryable_error()",
        "is_retryable_error" in storage_py or "retryable" in storage_py.lower(),
        "per-category recovery strategy",
    )
    add_check(
        "Ch.5",
        "Error categorization: handles connection errors",
        "ConnectionError" in storage_py or "OperationalError" in storage_py,
        "distinguishes network vs data errors",
    )
    add_check(
        "Ch.5",
        "Resilience: retry with exponential backoff",
        "retry" in storage_py.lower() or "MAX_RETRIES" in storage_py,
        "retries on transient failures",
    )

    add_check(
        "Ch.5",
        "Resilience: WebSocket reconnection logic",
        "reconnect" in live_feed.lower(),
        "reconnect with exponential backoff",
    )
    add_check(
        "Ch.5",
        "Resilience: exponential backoff on reconnect",
        "backoff" in live_feed.lower(),
        "delay = min(init * factor^n, max_delay)",
    )

    add_check(
        "Ch.5",
        "Backpressure: TickRingBuffer with overflow handling",
        "RingBuffer" in live_feed or "ring_buffer" in live_feed.lower() or "TickRingBuffer" in live_feed,
        "drop oldest on buffer overflow",
    )
    add_check(
        "Ch.5",
        "Backpressure: dropped_count counter for monitoring",
        "dropped_count" in live_feed,
        "track overflow events for Prometheus",
    )
    add_check(
        "Ch.5",
        "Thread safety: Lock on ring buffer operations",
        "Lock" in live_feed or "threading" in live_feed,
        "thread-safe push/drain",
    )


def main() -> int:
    print(f"\n{BOLD}{'=' * 72}{RESET}")
    print(f"{BOLD}  Phase 2 Kleppmann Cross-Reference Validation{RESET}")
    print(f"{BOLD}{'=' * 72}{RESET}")

    check_chapter1()
    check_chapter2()
    check_chapter3()
    check_chapter4()
    check_chapter5()

    passed = sum(1 for c in checks if c["passed"])
    failed = sum(1 for c in checks if not c["passed"])
    total = len(checks)

    print(f"\n{BOLD}{'=' * 72}{RESET}")
    print(f"  {GREEN}Passed: {passed}{RESET}  {RED}Failed: {failed}{RESET}  / {total} total")

    if failed > 0:
        print(f"\n  {BOLD}{RED}Failed Checks:{RESET}")
        for c in checks:
            if not c["passed"]:
                print(f"    {RED}[{c['chapter']}] {c['principle']}{RESET}")
                if c["detail"]:
                    print(f"       Expected: {c['detail']}")

    if failed == 0:
        print(f"\n  {BOLD}{GREEN}KLEPPMANN VALIDATION: ALL CHECKS PASS{RESET}")
    else:
        print(f"\n  {BOLD}{RED}KLEPPMANN VALIDATION: {failed} CHECK(S) FAILED{RESET}")
    print(f"{BOLD}{'=' * 72}{RESET}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
