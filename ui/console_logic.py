"""D37 §3 — logic thuần của SR Console, tách khỏi Streamlit để test offline.

Bất biến D37 §2 hiện thân ở đây:
1. Module KHÔNG import LLM client, KHÔNG chạy stage — chỉ đọc DB + ghi phán định người.
2. `CONSENSUS_APPROVED` chỉ do `approve_consensus()` ghi; hàm đó chỉ có đúng một
   caller là callback nút Tab 3 của `ui/sr_console.py`. Không có đường CLI tương
   đương (cấm scriptable — bất biến CLAUDE.md #6).
3. Overall RoB LUÔN do pure function của `rob_run` tính từ domain người chọn —
   người không bao giờ tự gõ overall.
4. Mọi hàm ghi gọi `assert_writable()` trước: lockfile single-writer tồn tại
   (orchestrator đang chạy) ⇒ console thành read-only (D39 §3).
"""

from __future__ import annotations

import os
from typing import Any

from sr_agent.store.staging import StagingStore
from sr_agent.store.writer_lock import holder
from tools.rob_run import compute_minors_overall, compute_rob2_overall

ROB2_DOMAINS = [
    "d1_randomization",
    "d2_deviations",
    "d3_missing_outcome",
    "d4_measurement",
    "d5_selection",
]

ROB2_CHOICES = ["Low", "Some concerns", "High", "VOID"]

# Trạng thái vòng đời run (D36) mà console được phép thao tác.
STATE_OPEN = "OPEN"
STATE_CONSENSUS_READY = "CONSENSUS_READY"
STATE_ABANDONED = "ABANDONED"


class WriteLocked(RuntimeError):
    """Orchestrator đang giữ lock ghi — console chỉ được đọc."""


def is_write_disabled(lock_info: dict | None, current_pid: int | None = None) -> bool:
    """Cùng ngữ nghĩa với `ui.app.is_write_disabled` — lock của tiến trình KHÁC ⇒ khóa."""
    if lock_info is None:
        return False
    if current_pid is None:
        return True
    return lock_info.get("pid") != current_pid


def assert_writable() -> None:
    if is_write_disabled(holder(), os.getpid()):
        raise WriteLocked(
            "Orchestrator đang giữ writer-lock — SR Console ở chế độ chỉ-đọc. "
            "Chờ pipeline chạy xong rồi thử lại."
        )


# --- Đọc: danh sách run + funnel ------------------------------------------------------


def list_runs(store: StagingStore) -> list[dict[str, Any]]:
    rows = store.conn.execute(
        "SELECT run_id, query, state, created_at FROM sr_runs ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_run(store: StagingStore, run_id: str) -> dict[str, Any] | None:
    row = store.conn.execute(
        "SELECT * FROM sr_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return dict(row) if row else None


FUNNEL_STAGES = [
    ("fetched", "FETCHED"),
    ("screened", "SCREEN_COMPLETED"),
    ("eligible", "ELIG_INCLUDED"),
    ("rob_done", "ROB_COMPLETED"),
    ("extracted", "EXTRACT_COMPLETED"),
]


def run_funnel(store: StagingStore, run_id: str) -> dict[str, int]:
    """Đếm doc riêng biệt ở từng bậc phễu — thuần từ events run-scoped (D36 §1)."""
    out: dict[str, int] = {}
    for label, event_type in FUNNEL_STAGES:
        row = store.conn.execute(
            "SELECT COUNT(DISTINCT uid) n FROM events WHERE event_type = ? AND run_id = ?",
            (event_type, run_id),
        ).fetchone()
        out[label] = row["n"] if row else 0
    return out


# --- Tab 1: phân xử RoB ---------------------------------------------------------------


def list_rob_escalations(store: StagingStore, run_id: str) -> list[dict[str, Any]]:
    """Doc ROB_ESCALATED của run, CHƯA được phân xử.

    Thứ tự (D37 §1 Tab 1): có ROB_PERTINENCE_FLAG trước (§4 — quote đúng nguồn
    nhưng lạc domain, người nên xem trước), rồi rubric_score giảm dần.
    """
    rows = store.conn.execute(
        """
        SELECT e.uid                          AS uid,
               d.title_normalized             AS title,
               d.rubric_score                 AS rubric_score,
               MAX(e.created_at)              AS escalated_at,
               MAX(e.detail)                  AS detail,
               (SELECT COUNT(*) FROM events p
                 WHERE p.uid = e.uid
                   AND p.event_type = 'ROB_PERTINENCE_FLAG'
                   AND p.run_id = ?)          AS n_pertinence_flags
        FROM events e
        LEFT JOIN documents d ON d.uid = e.uid
        WHERE e.event_type = 'ROB_ESCALATED' AND e.run_id = ?
        GROUP BY e.uid
        """,
        (run_id, run_id),
    ).fetchall()

    pending: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        if _has_completion_after(store, item["uid"], run_id, item["escalated_at"]):
            continue
        pending.append(item)

    pending.sort(
        key=lambda x: (
            0 if (x["n_pertinence_flags"] or 0) > 0 else 1,
            -(x["rubric_score"] or 0.0),
            x["uid"],
        )
    )
    return pending


def _has_completion_after(
    store: StagingStore, uid: str, run_id: str, escalated_at: str
) -> bool:
    """ROB_COMPLETED trong CÙNG run và SAU lần escalate cuối ⇒ đã phân xử.

    So sánh chuỗi ISO-8601 UTC là so sánh thời gian đúng (cùng offset, cùng độ dài).
    Ràng buộc run_id chặt: phán định ở run khác không được rửa nợ của run này.
    """
    row = store.conn.execute(
        """SELECT 1 FROM events
           WHERE uid = ? AND event_type = 'ROB_COMPLETED'
             AND run_id = ? AND created_at > ?
           LIMIT 1""",
        (uid, run_id, escalated_at),
    ).fetchone()
    return row is not None


def rob_pair_view(store: StagingStore, uid: str) -> dict[str, Any]:
    """Gom phán định máy A/B theo domain để người so cạnh nhau."""
    rows = store.get_rob_assessments(uid)
    view: dict[str, dict[str, Any]] = {}
    study_type = ""
    for r in rows:
        if r["agent"] not in ("rob_a", "rob_b"):
            continue
        study_type = study_type or (r["study_type"] or "")
        slot = view.setdefault(r["domain"], {})
        slot[r["agent"]] = {"verdict": r["verdict"], "quote": r["quote"] or ""}
    return {"study_type": study_type, "domains": view}


def compute_overall(study_type: str, verdicts: dict[str, str]) -> str:
    """MÁY tính overall từ domain người chọn (D37 §2.3) — người không được tự đặt."""
    if study_type == "RCT":
        missing = [d for d in ROB2_DOMAINS if d not in verdicts]
        if missing:
            raise ValueError(f"Thiếu phán định cho domain: {missing}")
        return compute_rob2_overall(*[verdicts[d] for d in ROB2_DOMAINS])
    if not verdicts:
        raise ValueError("Không có item MINORS nào được phán định.")
    return compute_minors_overall(dict(verdicts))


def save_human_adjudication(
    store: StagingStore,
    uid: str,
    study_type: str,
    verdicts: dict[str, str],
    run_id: str,
) -> str:
    """Ghi phán định người + overall tất định + event ROB_COMPLETED run-scoped.

    Trả về overall đã tính. VOID người chọn giữ nguyên ngữ nghĩa VOID — doc rơi
    khỏi phần số của consensus theo weighting BS4, KHÔNG bị "rửa" thành Low.
    """
    assert_writable()
    overall = compute_overall(study_type, verdicts)

    for domain, verdict in verdicts.items():
        store.add_rob_assessment(uid, "human", "human", study_type, domain, verdict, None)
    store.add_rob_assessment(uid, "human", "human", study_type, "__overall__", overall, None)

    store.log_event(uid, "ROB_COMPLETED", "human adjudication", run_id=run_id)
    return overall


# --- Tab 2: escalation khác (read-only + đánh dấu đã xem) -----------------------------

OTHER_ESCALATION_TYPES = [
    "ELIG_ESCALATED",
    "SCREEN_KAPPA_LOW",
    "SCREEN_DEGENERATE",
    "SCREEN_ESCALATED",
]


def list_other_escalations(store: StagingStore, run_id: str) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in OTHER_ESCALATION_TYPES)
    rows = store.conn.execute(
        f"""SELECT uid, event_type, detail, created_at FROM events
            WHERE event_type IN ({placeholders}) AND run_id = ?
            ORDER BY created_at DESC""",
        (*OTHER_ESCALATION_TYPES, run_id),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["acked"] = _is_acked(store, item["uid"], run_id, item["created_at"])
        out.append(item)
    return out


def _is_acked(store: StagingStore, uid: str, run_id: str, since: str) -> bool:
    row = store.conn.execute(
        """SELECT 1 FROM events
           WHERE uid = ? AND event_type = 'ESCALATION_ACKED'
             AND run_id = ? AND created_at > ? LIMIT 1""",
        (uid, run_id, since),
    ).fetchone()
    return row is not None


def ack_escalation(store: StagingStore, uid: str, run_id: str, note: str = "") -> None:
    assert_writable()
    store.log_event(uid, "ESCALATION_ACKED", note, run_id=run_id)


# --- Tab 3: cổng consensus ------------------------------------------------------------


def count_unverified_quotes(store: StagingStore, run_id: str) -> int:
    """Extraction chưa kiểm chứng được của doc thuộc run — thông tin cho người,
    KHÔNG phải điều kiện chặn (D37 §1 Tab 3: chỉ N escalation mới chặn)."""
    row = store.conn.execute(
        """SELECT COUNT(*) n FROM extraction
           WHERE verified != 1
             AND uid IN (SELECT DISTINCT uid FROM events WHERE run_id = ?)""",
        (run_id,),
    ).fetchone()
    return row["n"] if row else 0


def consensus_gate_status(store: StagingStore, run_id: str) -> dict[str, Any]:
    """Điều kiện ENABLE nút chốt — tất định, và luôn kèm lý do khi disable."""
    run = get_run(store, run_id)
    pending = list_rob_escalations(store, run_id)
    n_pending = len(pending)
    m_unverified = count_unverified_quotes(store, run_id)

    reasons: list[str] = []
    if run is None:
        reasons.append(f"Không tìm thấy run {run_id!r}.")
    elif run["state"] != STATE_OPEN:
        reasons.append(
            f"Run đang ở trạng thái {run['state']} — chỉ chốt được khi OPEN."
        )
    if n_pending > 0:
        reasons.append(f"Còn {n_pending} escalation RoB chưa phân xử.")

    return {
        "can_approve": not reasons,
        "reasons": reasons,
        "pending_escalations": n_pending,
        "unverified_quotes": m_unverified,
        "state": run["state"] if run else None,
    }


def approve_consensus(store: StagingStore, run_id: str) -> None:
    """CỔNG NGƯỜI — điểm ghi `CONSENSUS_APPROVED` DUY NHẤT của toàn hệ.

    Không được gọi từ bất kỳ đâu ngoài callback nút Tab 3 (bất biến #6). Fail-closed:
    điều kiện gate được kiểm lại NGAY TRONG hàm này, không tin vào trạng thái nút
    đã render (chống TOCTOU — sẹo OPS-1 2026-07-20).
    """
    assert_writable()
    status = consensus_gate_status(store, run_id)
    if not status["can_approve"]:
        raise ValueError("Không đủ điều kiện chốt: " + " ".join(status["reasons"]))

    store.log_event(
        f"consensus:{run_id}", "CONSENSUS_APPROVED", "human gate", run_id=run_id
    )
    store.conn.execute(
        "UPDATE sr_runs SET state = ? WHERE run_id = ?", (STATE_CONSENSUS_READY, run_id)
    )
    store.conn.commit()


def abandon_run(store: StagingStore, run_id: str, reason: str) -> None:
    assert_writable()
    if not reason.strip():
        raise ValueError("Hủy run bắt buộc kèm lý do.")
    store.log_event(f"consensus:{run_id}", "RUN_ABANDONED", reason, run_id=run_id)
    store.conn.execute(
        "UPDATE sr_runs SET state = ?, closed_at = datetime('now') WHERE run_id = ?",
        (STATE_ABANDONED, run_id),
    )
    store.conn.commit()
