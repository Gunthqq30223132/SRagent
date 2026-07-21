"""Staging Store — trụ cột state của SR-Agent (SQLite).

Ba bảng:
- documents : bản ghi Document (payload JSON) + cột truy vấn nhanh
              (status, rubric_score, fetched_at, last_interaction_at)
- dlq       : dead-letter queue cho bản ghi lỗi (cô lập, không nghẽn batch)
- events    : audit log (DEDUP_MERGED, APPROVED, PURGED, ...)

Cơ chế TTL: bản ghi CHƯA có tương tác Approve/Reject và quá TTL_HOURS kể từ
lần cập nhật cuối sẽ bị đánh EXPIRED rồi xóa. APPROVED/REJECTED giữ vĩnh viễn.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sr_agent.config import DB_PATH, TTL_HOURS, WIP_LIMIT
from sr_agent.models.schemas import DocStatus, Document

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    uid                 TEXT PRIMARY KEY,
    source              TEXT NOT NULL,
    title_normalized    TEXT NOT NULL,
    status              TEXT NOT NULL,
    rubric_score        REAL,
    payload             TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    last_interaction_at TEXT NOT NULL,
    notion_page_id      TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_score  ON documents(rubric_score);

CREATE TABLE IF NOT EXISTS dlq (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    uid            TEXT NOT NULL,
    error_type     TEXT NOT NULL,
    error_detail   TEXT NOT NULL,
    raw_path       TEXT,
    attempts       INTEGER NOT NULL DEFAULT 1,
    retry_eligible INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    uid        TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    run_id     TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);

CREATE TABLE IF NOT EXISTS sr_runs (
    run_id          TEXT PRIMARY KEY,
    query           TEXT NOT NULL,
    protocol_path   TEXT NOT NULL,
    protocol_sha256 TEXT NOT NULL,
    state           TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    closed_at       TEXT
);

-- M4: heartbeat batch (dead-man's switch) + standing query cho heal
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query       TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    report_json TEXT NOT NULL
);

-- M4: máy trạng thái alert — chỉ notify khi chuyển trạng thái (chống alarm fatigue)
CREATE TABLE IF NOT EXISTS alerts (
    key           TEXT PRIMARY KEY,
    state         TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '',
    first_seen    TEXT NOT NULL,
    last_notified TEXT
);

-- M6: Systematic Review sidecar tables
CREATE TABLE IF NOT EXISTS screening (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    verdict TEXT NOT NULL,
    criterion_id TEXT,
    evidence_quote TEXT,
    confidence TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    quote TEXT NOT NULL,
    section TEXT NOT NULL,
    verified INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rob_assessment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL,
    agent       TEXT NOT NULL,
    model       TEXT NOT NULL,
    study_type  TEXT NOT NULL,
    domain      TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    quote       TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rob_assessment_uid ON rob_assessment(uid);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StagingStore:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._apply_pragmas()

        # Idempotent migration: add run_id column to events table if table exists but column is missing
        cursor = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
        if cursor.fetchone():
            cursor = self.conn.execute("PRAGMA table_info(events)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "run_id" not in columns:
                self.conn.execute("ALTER TABLE events ADD COLUMN run_id TEXT")
                self.conn.commit()

        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def _apply_pragmas(self) -> None:
        """WAL + busy_timeout: cho phép ingest/orchestrator (ghi) và UI duyệt
        (đọc) truy cập cùng file DB đồng thời mà không 'database is locked'.

        journal_mode bền vững theo file (set một lần, mọi connection sau kế
        thừa); busy_timeout theo từng connection nên phải set mỗi lần mở. DB
        ':memory:' không hỗ trợ WAL và tự trả 'memory' — không lỗi, chấp nhận.
        """
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")  # 30s: khớp backoff MAX_RETRIES
        self.conn.execute("PRAGMA synchronous=NORMAL")  # an toàn dưới WAL, nhanh hơn FULL

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "StagingStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- documents -----------------------------------------------------------

    def upsert(self, doc: Document, *, touch: bool = True) -> None:
        now = _now()
        row = self.conn.execute(
            "SELECT last_interaction_at FROM documents WHERE uid = ?", (doc.uid,)
        ).fetchone()
        last_interaction = now if (touch or row is None) else row["last_interaction_at"]
        self.conn.execute(
            """INSERT INTO documents
               (uid, source, title_normalized, status, rubric_score, payload,
                fetched_at, last_interaction_at, notion_page_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(uid) DO UPDATE SET
                 title_normalized=excluded.title_normalized,
                 status=excluded.status,
                 rubric_score=excluded.rubric_score,
                 payload=excluded.payload,
                 last_interaction_at=excluded.last_interaction_at,
                 notion_page_id=excluded.notion_page_id""",
            (
                doc.uid,
                doc.source,
                doc.title_normalized,
                doc.status.value,
                doc.rubric.total if doc.rubric else None,
                doc.model_dump_json(),
                doc.fetched_at.isoformat(),
                last_interaction,
                doc.notion_page_id,
            ),
        )
        self.conn.commit()

    def get(self, uid: str) -> Document | None:
        row = self.conn.execute(
            "SELECT payload FROM documents WHERE uid = ?", (uid,)
        ).fetchone()
        return Document.model_validate_json(row["payload"]) if row else None

    def exists(self, uid: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM documents WHERE uid = ?", (uid,)
            ).fetchone()
            is not None
        )

    def all_uids(self) -> set[str]:
        return {r["uid"] for r in self.conn.execute("SELECT uid FROM documents")}

    def titles_index(self) -> dict[str, str]:
        """{title_normalized: uid} của các bản ghi còn sống — input cho D34 tầng 2."""
        rows = self.conn.execute(
            "SELECT uid, title_normalized FROM documents WHERE status != ?",
            (DocStatus.EXPIRED.value,),
        )
        return {r["title_normalized"]: r["uid"] for r in rows}

    def tiers_index(self) -> dict[str, int]:
        """{uid: authority_tier} — input cho tầng 3 của D34."""
        rows = self.conn.execute(
            "SELECT uid, json_extract(payload, '$.authority_tier') AS tier FROM documents"
        )
        return {r["uid"]: int(r["tier"]) for r in rows}

    def set_status(self, uid: str, status: DocStatus, *, touch: bool = True) -> None:
        doc = self.get(uid)
        if doc is None:
            return
        doc.status = status
        self.upsert(doc, touch=touch)

    # --- hàng đợi WIP ----------------------------------------------------------

    def get_wip_queue(self, limit: int = WIP_LIMIT) -> list[Document]:
        """Top bản ghi QUEUED theo điểm rubric giảm dần — nguồn dữ liệu cho QC UI."""
        rows = self.conn.execute(
            """SELECT payload FROM documents
               WHERE status = ?
                 AND uid NOT IN (
                     SELECT DISTINCT uid FROM events
                     WHERE run_id IN (SELECT run_id FROM sr_runs WHERE state = 'OPEN')
                 )
               ORDER BY rubric_score DESC, fetched_at ASC
               LIMIT ?""",
            (DocStatus.QUEUED.value, limit),
        )
        return [Document.model_validate_json(r["payload"]) for r in rows]

    def approved_today_count(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.conn.execute(
            """SELECT COUNT(*) AS n FROM events
               WHERE event_type = 'APPROVED' AND created_at >= ?""",
            (today,),
        ).fetchone()
        return row["n"]

    # --- TTL -------------------------------------------------------------------

    def purge_expired(self, ttl_hours: int = TTL_HOURS) -> list[str]:
        """Đánh EXPIRED + xóa bản ghi quá TTL không tương tác. Trả về uids đã purge.

        MIỄN TRỪ tuyến SR: doc đã có vết trong screening/extraction/rob_assessment
        thuộc corpus systematic-review đang chạy — các stage máy không cập nhật
        last_interaction_at, và một SR run hợp lệ kéo dài quá TTL (cổng người,
        escalation). TTL chỉ dọn hàng đợi triage đơn-tài-liệu chưa ai đụng tới.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
        terminal = (
            DocStatus.APPROVED.value,
            DocStatus.APPROVED_LOCAL.value,
            DocStatus.REJECTED.value,
        )
        rows = self.conn.execute(
            """SELECT uid FROM documents
               WHERE last_interaction_at < ? AND status NOT IN (?, ?, ?)
                 AND uid NOT IN (SELECT uid FROM screening)
                 AND uid NOT IN (SELECT uid FROM extraction)
                 AND uid NOT IN (SELECT uid FROM rob_assessment)
                 AND uid NOT IN (
                     SELECT DISTINCT uid FROM events
                     WHERE run_id IN (SELECT run_id FROM sr_runs WHERE state = 'OPEN')
                 )""",
            (cutoff, *terminal),
        ).fetchall()
        purged = [r["uid"] for r in rows]
        for uid in purged:
            self.log_event(uid, "PURGED", f"TTL {ttl_hours}h vượt hạn")
            self.conn.execute("DELETE FROM documents WHERE uid = ?", (uid,))
        self.conn.commit()
        return purged

    # --- DLQ ---------------------------------------------------------------------

    def push_dlq(
        self,
        uid: str,
        error_type: str,
        error_detail: str,
        *,
        raw_path: str | None = None,
        retry_eligible: bool = False,
    ) -> None:
        self.conn.execute(
            """INSERT INTO dlq (uid, error_type, error_detail, raw_path,
                                retry_eligible, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uid, error_type, error_detail, raw_path, int(retry_eligible), _now()),
        )
        self.conn.commit()

    def dlq_entries(self, *, retry_eligible_only: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM dlq"
        if retry_eligible_only:
            sql += " WHERE retry_eligible = 1"
        return self.conn.execute(sql + " ORDER BY created_at").fetchall()

    def clear_dlq_entry(self, entry_id: int) -> None:
        self.conn.execute("DELETE FROM dlq WHERE id = ?", (entry_id,))
        self.conn.commit()

    def bump_dlq_attempt(self, entry_id: int, *, max_attempts: int = 5) -> int:
        """Tăng attempts sau một lần retry fail; chạm trần -> tắt retry_eligible.

        Trả về số attempts mới. Chặn vòng retry vô hạn: entry chạm trần ở lại
        DLQ làm audit nhưng heal không đụng nữa (alert DLQ_PERMANENT lo phần báo).
        """
        row = self.conn.execute(
            "UPDATE dlq SET attempts = attempts + 1 WHERE id = ? "
            "RETURNING attempts", (entry_id,)
        ).fetchone()
        attempts = int(row["attempts"]) if row else 0
        if attempts >= max_attempts:
            self.conn.execute(
                "UPDATE dlq SET retry_eligible = 0 WHERE id = ?", (entry_id,)
            )
        self.conn.commit()
        return attempts

    # --- M4: degraded docs / runs ---------------------------------------------------

    def degraded_uids(self) -> list[str]:
        """Doc QUEUED xử lý heuristic-only (bỏ qua tầng LLM khi Ollama sập).

        Bất biến dữ liệu: tech_meta CHỈ được ghi bởi StructuralParser, chỉ cắm
        khi Ollama sống -> tech_meta IS NULL <=> chưa qua phân tích LLM.
        """
        rows = self.conn.execute(
            """SELECT uid FROM documents
               WHERE status = ? AND json_extract(payload, '$.tech_meta') IS NULL
               ORDER BY rubric_score DESC""",
            (DocStatus.QUEUED.value,),
        )
        return [r["uid"] for r in rows]

    def record_run(self, query: str, started_at: str, report_json: str) -> None:
        self.conn.execute(
            "INSERT INTO runs (query, started_at, finished_at, report_json) "
            "VALUES (?, ?, ?, ?)",
            (query, started_at, _now(), report_json),
        )
        self.conn.commit()

    def last_run(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    # --- events -------------------------------------------------------------------

    def log_event(self, uid: str, event_type: str, detail: str = "", run_id: str | None = None) -> None:
        import os
        rid = run_id if run_id is not None else os.getenv("SR_RUN_ID") or None
        self.conn.execute(
            "INSERT INTO events (uid, event_type, detail, run_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, event_type, detail, rid, _now()),
        )
        self.conn.commit()

    # --- M6 screening & extraction sidecar methods --------------------------------

    def add_screen_verdict(
        self,
        uid: str,
        agent: str,
        model: str,
        verdict: str,
        criterion_id: str | None = None,
        evidence_quote: str | None = None,
        confidence: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO screening
               (uid, agent, model, verdict, criterion_id, evidence_quote, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, agent, model, verdict, criterion_id, evidence_quote, confidence, _now()),
        )
        self.conn.commit()

    def screen_verdicts(self, uid: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM screening WHERE uid = ? ORDER BY created_at", (uid,)
        ).fetchall()

    def add_extraction(
        self,
        uid: str,
        field: str,
        value: str,
        quote: str,
        section: str,
        verified: int,
    ) -> None:
        self.conn.execute(
            """INSERT INTO extraction
               (uid, field, value, quote, section, verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid, field, value, quote, section, verified, _now()),
        )
        self.conn.commit()

    def extractions(self, uid: str, verified_only: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM extraction WHERE uid = ?"
        params = [uid]
        if verified_only:
            sql += " AND verified = 1"
        return self.conn.execute(sql + " ORDER BY created_at", params).fetchall()

    def screening_stats(self, hours: int = 24) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self.conn.execute(
            "SELECT uid, agent, verdict, confidence FROM screening WHERE created_at > ?",
            (cutoff,)
        ).fetchall()
        
        by_uid = {}
        for r in rows:
            by_uid.setdefault(r["uid"], {})[r["agent"]] = {
                "verdict": r["verdict"],
                "confidence": r["confidence"]
            }
        
        agreement_count = 0
        disagreement_resolved = 0
        escalated_count = 0
        
        for uid, agents in by_uid.items():
            a = agents.get("screener_a")
            b = agents.get("screener_b")
            tb = agents.get("tiebreaker")
            
            if not a or not b:
                continue
            
            if a["verdict"] == "invalid" or b["verdict"] == "invalid":
                escalated_count += 1
                continue
                
            if a["verdict"] == b["verdict"]:
                agreement_count += 1
            else:
                if tb:
                    if tb["verdict"] != "invalid" and tb["confidence"] == "high":
                        disagreement_resolved += 1
                    else:
                        escalated_count += 1
                else:
                    escalated_count += 1
                    
        return {
            "agreement": agreement_count,
            "disagreement_resolved": disagreement_resolved,
            "escalated": escalated_count
        }

    def get_escalated_uids(self) -> set[str]:
        rows = self.conn.execute(
            """SELECT DISTINCT d.uid FROM documents d
               JOIN events e ON d.uid = e.uid
               WHERE d.status = 'queued' AND e.event_type = 'SCREEN_ESCALATED'"""
        ).fetchall()
        return {r["uid"] for r in rows}

    def add_rob_assessment(
        self,
        uid: str,
        agent: str,
        model: str,
        study_type: str,
        domain: str,
        verdict: str,
        quote: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO rob_assessment
               (uid, agent, model, study_type, domain, verdict, quote, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, agent, model, study_type, domain, verdict, quote, _now()),
        )
        self.conn.commit()

    def get_rob_assessments(self, uid: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM rob_assessment WHERE uid = ? ORDER BY created_at", (uid,)
        ).fetchall()
