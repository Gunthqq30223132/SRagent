"""BS4 — Consensus Generator: CLI + điều phối (tầng KHÔNG thuần).

`python -m tools.consensus_run --protocol <path> --run <id> [--out <path>]`

Vị trí trong hệ: đây là nơi DUY NHẤT số lâm sàng đi vào văn bản đầu ra. Mọi đường
sinh số là code tất định (`tools/consensus_ledger.py`); LLM chỉ nối văn và LUÔN có
đường thoát không-LLM (fallback bảng tất định).

Không cờ CLI nào bỏ qua cổng người ở §1 — cấm scriptable (bất biến CLAUDE.md #6).
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from sr_agent.errors import ContextOverflowError
from sr_agent.parser.ollama_client import OllamaClient
from sr_agent.store.staging import StagingStore
from tools.consensus_ledger import (
    FALLBACK_SENTENCE,
    OVERALL_ROW,
    Claim,
    build_anchor_set,
    build_ledger,
    check_narrative,
    detect_conflicts,
    render_excluded,
    render_table,
)
from tools.prisma_report import generate_prisma_report

STATE_CONSENSUS_READY = "CONSENSUS_READY"
STATE_CLOSED = "CLOSED"
MAX_REWRITES = 2  # trần D32


class NarrativeOut(BaseModel):
    narrative: str


def get_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


# --- §1 Cổng vào ----------------------------------------------------------------------


def check_gate(store: StagingStore, run_id: str, protocol_path: Path) -> list[str]:
    """Ba điều kiện, thiếu bất kỳ điều nào ⇒ từ chối chạy. Trả về danh sách lý do."""
    problems: list[str] = []

    run = store.conn.execute(
        "SELECT * FROM sr_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if run is None:
        return [f"Không tìm thấy run {run_id!r} trong sr_runs."]

    if run["state"] == STATE_CLOSED:
        # §8: chạy lại trên run đã chốt ⇒ từ chối. Bất biến sau chốt; muốn làm lại
        # thì mở run mới, không ghi đè lịch sử.
        return [f"Run {run_id} đã CLOSED — báo cáo consensus là bất biến sau khi chốt."]

    approved = store.conn.execute(
        """SELECT 1 FROM events
           WHERE event_type = 'CONSENSUS_APPROVED' AND run_id = ? LIMIT 1""",
        (run_id,),
    ).fetchone()
    if approved is None:
        problems.append(
            "Thiếu event CONSENSUS_APPROVED — cổng người chưa chốt tập bằng chứng "
            "(mở SR Console: `make sr-ui`, Tab 3)."
        )

    if run["state"] != STATE_CONSENSUS_READY:
        problems.append(
            f"Trạng thái run là {run['state']}, cần {STATE_CONSENSUS_READY}."
        )

    if not protocol_path.exists():
        problems.append(f"Không thấy protocol tại {protocol_path}.")
    else:
        current = get_sha256(protocol_path)
        if current != run["protocol_sha256"]:
            problems.append(
                "protocol_sha256 lệch với lúc tạo run — protocol đã đổi SAU khi người "
                "chốt, nên phê duyệt đó không còn hiệu lực. "
                f"(run={run['protocol_sha256'][:12]}… hiện tại={current[:12]}…)"
            )

    return problems


# --- Thu thập dữ liệu cho ledger ------------------------------------------------------


def collect_rob_map(store: StagingStore, uids: list[str]) -> dict[str, str]:
    """uid → rob_overall. Phán định NGƯỜI (D37) thắng phán định máy (§3.2)."""
    out: dict[str, str] = {}
    for uid in uids:
        rows = store.get_rob_assessments(uid)
        human = [
            r for r in rows if r["agent"] == "human" and r["domain"] == OVERALL_ROW
        ]
        machine = [
            r for r in rows if r["agent"] == "rob_a" and r["domain"] == OVERALL_ROW
        ]
        chosen = human[-1] if human else (machine[-1] if machine else None)
        if chosen is not None:
            out[uid] = chosen["verdict"]
    return out


def collect_run_uids(store: StagingStore, run_id: str) -> list[str]:
    """Doc của run đã hoàn tất RoB — chỉ chúng mới đủ tư cách vào ledger (§3.1)."""
    rows = store.conn.execute(
        """SELECT DISTINCT uid FROM events
           WHERE event_type = 'ROB_COMPLETED' AND run_id = ? ORDER BY uid""",
        (run_id,),
    ).fetchall()
    return [r["uid"] for r in rows]


def collect_extractions(store: StagingStore, uids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for uid in uids:
        for row in store.extractions(uid, verified_only=False):
            item = dict(row)
            item["uid"] = uid
            out.append(item)
    return out


def persist_claims(store: StagingStore, claims: list[Claim]) -> None:
    """Ghi ledger TRƯỚC khi sinh narrative — ledger là sự thật, văn là dẫn xuất (§7)."""
    for c in claims:
        store.conn.execute(
            """INSERT OR REPLACE INTO consensus_claim
               (claim_id, run_id, outcome_id, uid, field, value, quote,
                rob_overall, weight, direction, conflict_group, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))""",
            (
                c.claim_id, c.run_id, c.outcome_id, c.uid, c.field, c.value,
                c.quote, c.rob_overall, c.weight, c.direction, c.conflict_group,
            ),
        )
    store.conn.commit()


# --- §6 Narrative: LLM là trang sức, không phải trụ ------------------------------------

SYSTEM_PROMPT = (
    "You are drafting the narrative section of a systematic review. "
    "You MUST obey every rule below; violating any one voids the entire output.\n"
    "1. Use ONLY numbers that appear verbatim in the table provided. Never compute, "
    "average, pool, or compare magnitudes across studies.\n"
    "2. Every sentence containing a number MUST cite its claim as [clm-...].\n"
    "3. Never use approximation words (approximately, about, around, roughly, ~).\n"
    "4. For any group marked 'CONFLICTING — not pooled', you MUST present both sides "
    "in a single sentence citing at least two claim ids. Never omit a conflict.\n"
    "5. Do not state a direction of effect for any row whose direction column is '—'."
)


def build_user_prompt(table_md: str, retry_reasons: list[str] | None = None) -> str:
    parts = ["Evidence table:\n", table_md]
    if retry_reasons:
        parts.append(
            "\n\nYour previous draft was REJECTED for the following reasons. "
            "Fix all of them:\n- " + "\n- ".join(retry_reasons)
        )
    return "".join(parts)


def generate_narrative(
    claims: list[Claim],
    table_md: str,
    anchor_set: set[str],
    client: OllamaClient | None,
) -> tuple[str, str, list[str]]:
    """Trả về (narrative, mode, lý do fallback). mode ∈ {'llm', 'fallback'}.

    Reject ⇒ rewrite kèm lý do, tối đa MAX_REWRITES lần. Hết lượt (hoặc overflow /
    Ollama sập) ⇒ narrative = bảng đã render + câu khung tất định. Báo cáo LUÔN ra —
    không có chế độ "chờ LLM".
    """
    if client is None:
        return _fallback(table_md), "fallback", ["Không có LLM client."]

    reasons: list[str] = []
    for attempt in range(MAX_REWRITES + 1):
        try:
            result = client.generate_structured(
                SYSTEM_PROMPT, build_user_prompt(table_md, reasons or None), NarrativeOut
            )
        except ContextOverflowError as exc:
            return _fallback(table_md), "fallback", [f"context overflow: {exc}"]
        except Exception as exc:  # Ollama sập / schema sai / mạng
            return _fallback(table_md), "fallback", [f"LLM lỗi: {exc}"]

        problems = check_narrative(result.narrative, claims, anchor_set)
        if not problems:
            return result.narrative, "llm", []
        reasons = problems

    return _fallback(table_md), "fallback", reasons


def _fallback(table_md: str) -> str:
    return f"{FALLBACK_SENTENCE}\n\n{table_md}"


# --- §7 Báo cáo -----------------------------------------------------------------------


def build_report(
    run_row: Any,
    run_id: str,
    protocol_sha: str,
    narrative: str,
    table_md: str,
    claims: list[Claim],
    prisma_md: str,
    mode: str,
) -> str:
    n_conflicts = len({c.conflict_group for c in claims if c.conflict_group})
    quotes = "\n".join(
        f"- **[{c.claim_id}]** `{c.uid}` — {c.quote}" for c in sorted(claims, key=lambda x: x.claim_id)
    )
    return f"""# Consensus report — {run_id}

| | |
|---|---|
| run_id | `{run_id}` |
| query | {run_row['query']} |
| protocol_sha256 | `{protocol_sha}` |
| git HEAD | `{_git_head()}` |
| ngày | {date.today().isoformat()} |
| claims | {len(claims)} |
| nhóm xung đột | {n_conflicts} |
| narrative mode | `{mode}` |

## PRISMA (per-run)

{prisma_md}

## Narrative

{narrative}

## Ledger đầy đủ

{table_md}

## Phụ lục A — Excluded (weight 0)

{render_excluded(claims)}

## Phụ lục B — quote nguyên văn

{quotes or '_không có claim_'}
"""


# --- CLI ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BS4 — sinh báo cáo đồng thuận cho một SR run")
    ap.add_argument("--protocol", required=True, type=Path)
    ap.add_argument("--run", required=True, dest="run_id")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-llm", action="store_true", help="bỏ qua LLM, dùng thẳng bảng tất định")
    args = ap.parse_args(argv)

    store = StagingStore()

    problems = check_gate(store, args.run_id, args.protocol)
    if problems:
        print("❌ Không đủ điều kiện tổng hợp:", file=sys.stderr)
        for p in problems:
            print(f"   · {p}", file=sys.stderr)
        return 2

    run_row = store.conn.execute(
        "SELECT * FROM sr_runs WHERE run_id = ?", (args.run_id,)
    ).fetchone()

    from tools.protocol_build import ReviewProtocol

    protocol = ReviewProtocol.model_validate_json(
        args.protocol.read_text(encoding="utf-8")
    )

    uids = collect_run_uids(store, args.run_id)
    claims = build_ledger(
        collect_extractions(store, uids),
        collect_rob_map(store, uids),
        protocol,
        args.run_id,
    )
    claims = detect_conflicts(claims)
    persist_claims(store, claims)

    table_md = render_table(claims)
    anchors = build_anchor_set(claims, getattr(protocol, "unit_lexicon", []))

    client = None if args.no_llm else OllamaClient()
    narrative, mode, reasons = generate_narrative(claims, table_md, anchors, client)
    if mode == "fallback":
        store.log_event(
            f"consensus:{args.run_id}",
            "CONSENSUS_NARRATIVE_FALLBACK",
            "; ".join(reasons)[:400],
            run_id=args.run_id,
        )

    report = build_report(
        run_row, args.run_id, run_row["protocol_sha256"], narrative,
        table_md, claims, generate_prisma_report(store, run_id=args.run_id), mode,
    )

    out_path = args.out or Path("docs/runs") / f"{date.today().isoformat()}-consensus-{args.run_id}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    n_conflicts = len({c.conflict_group for c in claims if c.conflict_group})
    store.log_event(
        f"consensus:{args.run_id}",
        "CONSENSUS_COMPLETED",
        f"claims={len(claims)} conflicts={n_conflicts} mode={mode}",
        run_id=args.run_id,
    )
    store.conn.execute(
        "UPDATE sr_runs SET state = ?, closed_at = datetime('now') WHERE run_id = ?",
        (STATE_CLOSED, args.run_id),
    )
    store.conn.commit()

    print(f"✅ Báo cáo: {out_path}")
    print(f"   claims={len(claims)} conflicts={n_conflicts} mode={mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
