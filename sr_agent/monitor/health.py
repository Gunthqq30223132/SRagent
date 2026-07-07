"""Health snapshot — trạng thái hệ thống đọc THUẦN từ SQLite, không probe mạng.

Mọi tín hiệu suy ra từ dữ liệu pipeline đã ghi sẵn (dlq/events/runs/documents),
nên snapshot chạy được cả khi hạ tầng sập hoàn toàn — đúng lúc cần nó nhất.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sr_agent.config import CIRCUIT_BREAKER_FAILURES
from sr_agent.store.staging import StagingStore

NO_BATCH_ALERT_HOURS = 36  # dead-man's switch: quá lâu không có batch nào chạy


@dataclass
class HealthSnapshot:
    dlq_total: int = 0
    dlq_retry_eligible: int = 0
    dlq_by_error: dict[str, int] = field(default_factory=dict)
    dlq_last_24h: int = 0
    dlq_permanent: int = 0            # entry chạm trần attempts, đã tắt retry
    degraded_count: int = 0           # doc QUEUED chưa qua tầng LLM
    sources_down: list[str] = field(default_factory=list)
    status_counts: dict[str, int] = field(default_factory=dict)
    last_run: sqlite3.Row | None = None
    hours_since_last_run: float | None = None
    screen_kappa_recent: float | None = None
    screen_kappa_docs_count: int = 0
    screen_escalated_count: int = 0
    grounding_avg_24h: float | None = None
    extraction_docs_count_24h: int = 0


def _cutoff(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def snapshot(store: StagingStore) -> HealthSnapshot:
    snap = HealthSnapshot()
    conn = store.conn

    for row in conn.execute(
        "SELECT error_type, COUNT(*) n, SUM(retry_eligible) elig FROM dlq GROUP BY error_type"
    ):
        snap.dlq_by_error[row["error_type"]] = row["n"]
        snap.dlq_total += row["n"]
        snap.dlq_retry_eligible += row["elig"] or 0

    day_ago = _cutoff(24)
    snap.dlq_last_24h = conn.execute(
        "SELECT COUNT(*) n FROM dlq WHERE created_at > ?", (day_ago,)
    ).fetchone()["n"]
    snap.dlq_permanent = conn.execute(
        "SELECT COUNT(*) n FROM dlq WHERE retry_eligible = 0 AND attempts >= 5",
    ).fetchone()["n"]

    # Nguồn sập trong 24h: entry batch-level HOẶC >= ngưỡng circuit breaker
    # doc-level cùng nguồn (vết cầu dao suy từ dữ liệu, không cần sửa pipeline)
    down: set[str] = set()
    for row in conn.execute(
        "SELECT uid FROM dlq WHERE retry_eligible = 1 AND created_at > ? "
        "AND uid LIKE '%:batch'", (day_ago,),
    ):
        down.add(row["uid"].split(":", 1)[0])
    for row in conn.execute(
        """SELECT substr(uid, 1, instr(uid, ':') - 1) AS src, COUNT(*) n
           FROM dlq WHERE retry_eligible = 1 AND created_at > ?
             AND uid NOT LIKE '%:batch'
           GROUP BY src HAVING n >= ?""",
        (day_ago, CIRCUIT_BREAKER_FAILURES),
    ):
        down.add(row["src"])
    snap.sources_down = sorted(down)

    snap.degraded_count = len(store.degraded_uids())

    for row in conn.execute("SELECT status, COUNT(*) n FROM documents GROUP BY status"):
        snap.status_counts[row["status"]] = row["n"]

    snap.last_run = store.last_run()
    if snap.last_run is not None:
        started = datetime.fromisoformat(snap.last_run["started_at"])
        snap.hours_since_last_run = (
            datetime.now(timezone.utc) - started
        ).total_seconds() / 3600

    # M6: screening & extraction health metrics
    snap.screen_escalated_count = len(store.get_escalated_uids())

    all_verdicts = conn.execute(
        """SELECT uid, agent, verdict FROM screening 
           WHERE agent IN ('screener_a', 'screener_b') AND verdict IN ('include', 'exclude')"""
    ).fetchall()
    grouped = {}
    for r in all_verdicts:
        grouped.setdefault(r["uid"], {})[r["agent"]] = r["verdict"]
    pairs = [
        (grouped[u]["screener_a"], grouped[u]["screener_b"])
        for u in grouped
        if "screener_a" in grouped[u] and "screener_b" in grouped[u]
    ]
    snap.screen_kappa_recent = _compute_cohen_kappa(pairs)
    snap.screen_kappa_docs_count = len(pairs)

    day_ago = _cutoff(24)
    ext_rows = conn.execute(
        "SELECT uid, verified FROM extraction WHERE created_at > ?", (day_ago,)
    ).fetchall()
    ext_grouped = {}
    for r in ext_rows:
        ext_grouped.setdefault(r["uid"], []).append(r["verified"])
    
    scores = []
    for uid, verifieds in ext_grouped.items():
        if verifieds:
            scores.append(sum(verifieds) / len(verifieds))
    snap.grounding_avg_24h = sum(scores) / len(scores) if scores else None
    snap.extraction_docs_count_24h = len(ext_grouped)

    return snap


def _compute_cohen_kappa(verdicts: list[tuple[str, str]]) -> float | None:
    N = len(verdicts)
    if N < 2:
        return None
    
    n_11 = sum(1 for a, b in verdicts if a == "include" and b == "include")
    n_12 = sum(1 for a, b in verdicts if a == "include" and b == "exclude")
    n_21 = sum(1 for a, b in verdicts if a == "exclude" and b == "include")
    n_22 = sum(1 for a, b in verdicts if a == "exclude" and b == "exclude")
    
    p_o = (n_11 + n_22) / N
    p_inc_a = (n_11 + n_12) / N
    p_inc_b = (n_11 + n_21) / N
    p_exc_a = (n_21 + n_22) / N
    p_exc_b = (n_12 + n_22) / N
    
    p_e = p_inc_a * p_inc_b + p_exc_a * p_exc_b
    if abs(1.0 - p_e) < 1e-9:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)
