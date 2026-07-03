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
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StagingStore:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

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
        """Đánh EXPIRED + xóa bản ghi quá TTL không tương tác. Trả về uids đã purge."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
        terminal = (
            DocStatus.APPROVED.value,
            DocStatus.APPROVED_LOCAL.value,
            DocStatus.REJECTED.value,
        )
        rows = self.conn.execute(
            """SELECT uid FROM documents
               WHERE last_interaction_at < ? AND status NOT IN (?, ?, ?)""",
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

    # --- events -------------------------------------------------------------------

    def log_event(self, uid: str, event_type: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO events (uid, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
            (uid, event_type, detail, _now()),
        )
        self.conn.commit()
