"""BS2 — SR Pipeline Orchestrator (`tools/sr_run.py`).

Điều phối toàn tuyến systematic-review như một **state machine theo DocStatus**.
Các giai đoạn (ingest, screening, eligibility, extraction, …) đã tồn tại dưới dạng
runner độc lập có `main(argv) -> int`; orchestrator này chỉ *xâu chuỗi* chúng theo
đúng thứ tự và **DỪNG ở mỗi cổng người duyệt**.

Bất biến cứng (CLAUDE.md):
- **#6 Người duyệt là cổng bất biến.** Orchestrator KHÔNG BAO GIỜ tự tạo trạng
  thái do người quyết định. Cổng người (`consensus_review`) chỉ được coi là "đã
  qua" khi orchestrator *đọc thấy* trạng thái đó đã tồn tại — nó không bao giờ
  *tạo ra* trạng thái đó.
- **#3 Topic-blind.** File này chỉ biết "có N phase, phase nào là cổng người" —
  không mang ngữ nghĩa miền; ngữ nghĩa nằm trong protocol JSON mà runner con nạp.
- Idempotent/resumable: mỗi runner con lọc theo DocStatus nên chạy lại an toàn;
  `--from <phase>` cho phép tiếp tục sau khi người đã duyệt.

Ghi chú thiết kế (sửa sau lượt review đầu): `screen`/`eligibility`/`rob` đều lọc
input theo `status='queued'` (xem `tools/screen_run.py`), KHÔNG theo `APPROVED`.
`DocStatus.APPROVED` chỉ được set ở `sr_agent/publish/notion_page.py` — hành
động "Approve" của `make ui` là xuất bản sang Notion (nhánh xuất bản đơn-tài-liệu
độc lập, không thuộc tuyến SR), và nó CHUYỂN doc ra khỏi `queued`. Vì vậy tuyến
SR không đặt cổng người giữa `ingest` và `screen` — cổng người của tuyến SR nằm
ở cuối, `consensus_review`, trước khi tổng hợp bằng chứng (BS4).

Đây là *khung* BS2: các phase `rob`/`consensus` được khai báo trong đồ thị nhưng
tự nhận diện "chưa triển khai" (module chưa có) và dừng sạch — ranh giới hệ hiện tại.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sr_agent.models.schemas import DocStatus  # noqa: E402
from sr_agent.store import writer_lock  # noqa: E402
from sr_agent.store.staging import StagingStore  # noqa: E402

# Trạng thái "hậu cổng người": sự tồn tại của bất kỳ doc nào ở đây = người ĐÃ
# ra ít nhất một quyết định duyệt. Orchestrator chỉ đọc, không tạo.
_APPROVED_STATES = (DocStatus.APPROVED.value, DocStatus.APPROVED_LOCAL.value)

AUTO = "auto"
HUMAN_GATE = "human_gate"

# Trạng thái run mà `--run <id>` được phép chạy tiếp.
# CONSENSUS_READY BẮT BUỘC có mặt: đó chính là trạng thái người tạo ra khi bấm chốt
# ở SR Console (D37). Nếu chỉ nhận OPEN thì đúng luồng mà D37+BS4 sinh ra để phục vụ
# — người duyệt xong rồi chạy tiếp `--from consensus` — lại bị từ chối (FL-SIM 2026-07-29).
# CLOSED và ABANDONED vắng mặt có chủ đích: báo cáo là bất biến sau khi chốt.
RESUMABLE_STATES = frozenset({"OPEN", "CONSENSUS_READY"})


@dataclass
class Phase:
    name: str
    kind: str  # AUTO | HUMAN_GATE
    desc: str
    # AUTO: nạp runner con lười (module_path, attr) và dựng argv từ CLI args.
    runner_ref: tuple[str, str] | None = None
    build_args: Callable[[argparse.Namespace], list[str]] | None = None
    # HUMAN_GATE: vị ngữ CHỈ ĐỌC xác định người đã ra quyết định chưa.
    satisfied: Callable[[StagingStore], bool] | None = None
    resume_hint: str = ""  # phase để chạy tiếp sau khi qua cổng

    def is_available(self) -> bool:
        """AUTO: module runner đã tồn tại chưa (phase tương lai trả False)."""
        if self.kind != AUTO or self.runner_ref is None:
            return True
        module_path, _ = self.runner_ref
        return importlib.util.find_spec(module_path) is not None

    def resolve_runner(self) -> Callable[[list[str]], int]:
        module_path, attr = self.runner_ref  # type: ignore[misc]
        module = importlib.import_module(module_path)
        return getattr(module, attr)


def _has_approved(store: StagingStore) -> bool:
    row = store.conn.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE status IN (?, ?)",
        _APPROVED_STATES,
    ).fetchone()
    return bool(row["n"])


def is_consensus_approved(store: StagingStore) -> bool:
    run_id = os.getenv("SR_RUN_ID")
    if not run_id:
        return False
    row = store.conn.execute(
        "SELECT 1 FROM events WHERE run_id = ? AND event_type = 'CONSENSUS_APPROVED' LIMIT 1",
        (run_id,)
    ).fetchone()
    return row is not None


def get_sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read())
    return h.hexdigest()


def build_phases() -> list[Phase]:
    """Đồ thị chuẩn của tuyến SR — nguồn sự thật duy nhất về thứ tự giai đoạn.

    Không có cổng người giữa `ingest` và `screen`: cả hai lọc/ghi trên
    `status='queued'` trực tiếp (screen/eligibility/rob không yêu cầu APPROVED —
    xem docstring module). Cổng người của tuyến SR là `consensus_review`, cuối
    tuyến, trước khi tổng hợp (BS4).
    """
    return [
        Phase(
            name="ingest",
            kind=AUTO,
            desc="Thu thập + dedup + rubric + parse → hàng đợi QUEUED.",
            runner_ref=("sr_agent.pipeline", "main"),
            build_args=lambda a: ["run", "--query", a.query, "--max-results", str(a.max_results)],
        ),
        Phase(
            name="screen",
            kind=AUTO,
            desc="Song thẩm A/B trên doc QUEUED (title/abstract).",
            runner_ref=("tools.screen_run", "main"),
            build_args=lambda a: ["--protocol", str(a.protocol), "--limit", str(a.limit)],
        ),
        Phase(
            name="eligibility",
            kind=AUTO,
            desc="Sàng full-text theo tiêu chí loại trừ.",
            runner_ref=("tools.eligibility_run", "main"),
            build_args=lambda a: ["--protocol", str(a.protocol), "--limit", str(a.limit)],
        ),
        Phase(
            name="rob",
            kind=AUTO,
            desc="Đánh giá Risk-of-Bias (BS3) — hạ trọng số study thiên lệch.",
            runner_ref=("tools.rob_run", "main"),
            build_args=lambda a: ["--protocol", str(a.protocol), "--limit", str(a.limit)],
        ),
        Phase(
            # FL-1 2026-07-19: dời extract xuống SAU rob theo đúng ý đồ BS3 §0
            # (chấm độ tin cậy study trước khi số liệu của nó được trích/tin).
            name="extract",
            kind=AUTO,
            desc="Trích dữ liệu có thuế bằng chứng (evidenced extraction).",
            runner_ref=("tools.evidence_extract", "main"),
            # D40: KHÔNG truyền --protocol thì evidence_extract rơi về
            # LEGACY_EXTRACTION_FIELDS (taxonomy CS) — run y khoa sẽ trích nhầm
            # has_code_repo/dataset_spec thay vì liều/kết cục. Phát hiện khi nối BS4.
            build_args=lambda a: ["--protocol", str(a.protocol), "--limit", str(a.limit)],
        ),
        Phase(
            name="consensus_review",
            kind=HUMAN_GATE,
            desc="CON NGƯỜI xác nhận tập bằng chứng trước khi tổng hợp (BS4). "
            "Cổng người thứ hai — không tự vượt.",
            satisfied=is_consensus_approved,
            resume_hint="consensus",
        ),
        Phase(
            name="consensus",
            kind=AUTO,
            desc="Tổng hợp đồng thuận + firewall số (BS4).",
            runner_ref=("tools.consensus_run", "main"),
            # run_id chỉ nằm trong env khi tạo run mới (args.run là None ở nhánh đó),
            # nên đọc env trước — build_args được gọi lúc chạy phase, sau khi env đã set.
            build_args=lambda a: [
                "--protocol", str(a.protocol),
                "--run", os.environ.get("SR_RUN_ID") or getattr(a, "run", "") or "",
            ],
        ),
    ]


def _status_counts_for_run(store: StagingStore, run_id: str) -> dict[str, int]:
    rows = store.conn.execute(
        """SELECT d.status, COUNT(DISTINCT d.uid) AS n
           FROM documents d
           JOIN events e ON d.uid = e.uid
           WHERE e.run_id = ?
           GROUP BY d.status""",
        (run_id,)
    ).fetchall()
    return {r["status"]: r["n"] for r in rows}


def _status_counts(store: StagingStore) -> dict[str, int]:
    rows = store.conn.execute(
        "SELECT status, COUNT(*) AS n FROM documents GROUP BY status"
    )
    return {r["status"]: r["n"] for r in rows}


def cmd_plan(phases: list[Phase]) -> int:
    print("Đồ thị tuyến SR (BS2 orchestrator):\n")
    for i, ph in enumerate(phases, 1):
        if ph.kind == HUMAN_GATE:
            tag = "⛔ CỔNG NGƯỜI"
        elif not ph.is_available():
            tag = "… chưa triển khai"
        else:
            tag = "▶ tự động"
        print(f"  {i}. [{tag}] {ph.name} — {ph.desc}")
    print("\nCổng người = orchestrator DỪNG; người duyệt rồi chạy lại `--from <phase>`.")
    return 0


def cmd_status(store: StagingStore, phases: list[Phase], run_id: str | None = None) -> int:
    if run_id:
        os.environ["SR_RUN_ID"] = run_id
        counts = _status_counts_for_run(store, run_id)
        # Check if the run exists
        run = store.conn.execute("SELECT * FROM sr_runs WHERE run_id = ?", (run_id,)).fetchone()
        if run:
            print(f"Run ID: {run_id} ({run['state']})")
            print(f"Query: {run['query']}")
            print(f"Protocol: {run['protocol_path']} (SHA: {run['protocol_sha256'][:8]}...)")
            print()
    else:
        counts = _status_counts(store)

    print("documents theo DocStatus:")
    for status, n in sorted(counts.items()):
        print(f"  {status:>16}: {n}")
    if not counts:
        print("  (trống — chưa ingest)")
    print()
    for ph in phases:
        if ph.kind != HUMAN_GATE:
            continue
        ok = bool(ph.satisfied and ph.satisfied(store))
        print(f"cổng {ph.name!r}: {'✅ đã qua' if ok else '⛔ chưa'}")
    return 0


def cmd_runs(store: StagingStore) -> int:
    rows = store.conn.execute(
        "SELECT run_id, query, state, created_at FROM sr_runs ORDER BY created_at DESC"
    ).fetchall()
    if not rows:
        print("Không có SR run nào.")
        return 0
    print(f"{'RUN ID':<30} | {'STATE':<15} | {'CREATED AT':<25} | {'QUERY'}")
    print("-" * 90)
    for r in rows:
        print(f"{r['run_id']:<30} | {r['state']:<15} | {r['created_at']:<25} | {r['query']}")
    return 0


def run_pipeline(
    store: StagingStore,
    phases: list[Phase],
    args: argparse.Namespace,
    start_from: str | None = None,
) -> int:
    """Chạy các phase AUTO theo thứ tự, DỪNG ở cổng người chưa thỏa.

    - `start_from` cho phép tiếp tục sau khi người đã duyệt. Nhưng MỌI cổng người
      NẰM TRƯỚC điểm bắt đầu vẫn bị kiểm: chưa thỏa ⇒ từ chối (không cho lách cổng).
    - Cổng người chỉ "đã qua" khi vị ngữ chỉ-đọc `satisfied(store)` = True (đọc
      trạng thái do người tạo). Không có đường nào ở đây tự set APPROVED.
    """
    if start_from and not any(p.name == start_from for p in phases):
        print(f"❌ Không có phase tên {start_from!r}.")
        return 2

    reached_start = start_from is None
    for ph in phases:
        # "seeking" = phase nằm strictly TRƯỚC điểm bắt đầu (đang tua tới).
        at_or_past = reached_start or ph.name == start_from
        if ph.name == start_from:
            reached_start = True
        seeking = not at_or_past

        if ph.kind == HUMAN_GATE:
            ok = bool(ph.satisfied and ph.satisfied(store))
            if seeking:
                # Tua qua cổng nằm trước điểm bắt đầu, nhưng KHÔNG được lách cổng chưa thỏa.
                if not ok:
                    print(
                        f"⛔ Không thể bỏ qua cổng người {ph.name!r}: chưa thỏa "
                        f"(chưa có quyết định duyệt). Hãy duyệt trước rồi chạy lại."
                    )
                    return 2
                continue
            if ok:
                print(f"✅ Cổng người {ph.name!r} đã thỏa — tiếp tục.")
                continue
            print(f"⏸  DỪNG ở cổng người {ph.name!r}.\n    {ph.desc}")
            if ph.resume_hint:
                print(f"    → Sau khi duyệt xong, chạy lại: sr_run run --from {ph.resume_hint} …")
            return 0

        # --- AUTO phase ---
        if seeking:
            continue

        if not ph.is_available():
            print(
                f"⏸  Phase {ph.name!r} chưa triển khai (module chưa có) — ranh giới hệ hiện tại. Dừng."
            )
            return 0

        runner = ph.resolve_runner()
        argv = ph.build_args(args) if ph.build_args else []
        print(f"▶ Phase {ph.name!r}: {ph.name} {' '.join(argv)}")
        rc = runner(argv)
        if rc != 0:
            print(f"❌ Phase {ph.name!r} thất bại (rc={rc}). Dừng tuyến.")
            return rc

    print("✅ Đã chạy hết các phase khả dụng.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sr_run", description="BS2 — SR pipeline orchestrator (state machine theo DocStatus)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("plan", help="in đồ thị các phase + cổng người")
    
    st = sub.add_parser("status", help="đếm documents theo DocStatus + trạng thái cổng")
    st.add_argument("--db", type=Path, help="override DB path")
    st.add_argument("--run", help="Chỉ xem status cho run cụ thể")

    runs_p = sub.add_parser("runs", help="liệt kê các sr_runs")
    runs_p.add_argument("--db", type=Path, help="override DB path")

    run_p = sub.add_parser("run", help="chạy tuyến, dừng ở cổng người chưa thỏa")
    run_p.add_argument("--query", default="", help="truy vấn ingest (phase đầu)")
    run_p.add_argument("--max-results", type=int, default=20)
    run_p.add_argument("--protocol", type=Path, help="protocol JSON cho screen/eligibility/rob")
    run_p.add_argument("--limit", type=int, default=10)
    run_p.add_argument("--from", dest="start_from", default=None,
                       help="tiếp tục từ phase này (sau khi đã duyệt)")
    run_p.add_argument("--db", type=Path, help="override DB path")
    run_p.add_argument("--run", help="Resume an existing run_id")

    args = ap.parse_args(argv)
    phases = build_phases()

    if args.cmd == "plan":
        return cmd_plan(phases)

    # `--db` phải chi phối CẢ TUYẾN, không riêng store của orchestrator: mỗi phase
    # con tự mở `StagingStore()` trong tiến trình này, nên truyền qua env là đường
    # duy nhất tới được chúng. Thiếu dòng này thì orchestrator ghi một DB còn các
    # stage ghi DB khác — im lặng, không lỗi, và mọi số đếm đều sai.
    if getattr(args, "db", None):
        os.environ["SR_AGENT_DB"] = str(args.db)
    db_kwargs = {"db_path": args.db} if getattr(args, "db", None) else {}
    with StagingStore(**db_kwargs) as store:
        if args.cmd == "status":
            return cmd_status(store, phases, getattr(args, "run", None))
        if args.cmd == "runs":
            return cmd_runs(store)
        if args.cmd == "run":
            if not writer_lock.acquire("orchestrator"):
                lock_info = writer_lock.holder()
                print(f"❌ Không thể acquire writer lock — đang được giữ bởi: {lock_info}")
                return 2
            try:
                import random
                from datetime import datetime, timezone
                
                run_id = getattr(args, "run", None)
                if run_id:
                    # Resume existing run
                    run_row = store.conn.execute("SELECT * FROM sr_runs WHERE run_id = ?", (run_id,)).fetchone()
                    if not run_row:
                        print(f"❌ Lỗi: Không tìm thấy run_id={run_id!r} trong sr_runs.")
                        return 2
                    if run_row["state"] not in RESUMABLE_STATES:
                        print(f"❌ Lỗi: Run {run_id} đang ở trạng thái {run_row['state']!r}, không thể resume.")
                        return 2
                    if not args.protocol or not args.protocol.exists():
                        print("❌ Lỗi: Cần truyền --protocol hợp lệ để đối chiếu.")
                        return 2
                    current_sha = get_sha256(args.protocol)
                    if current_sha != run_row["protocol_sha256"]:
                        print(f"❌ Lỗi: Protocol SHA256 không khớp! Gốc: {run_row['protocol_sha256']}, Hiện tại: {current_sha}")
                        return 2
                    
                    print(f"⏯  Resume run: {run_id}")
                    os.environ["SR_RUN_ID"] = run_id
                    args.query = run_row["query"]
                else:
                    # Start new run
                    if args.start_from is not None:
                        print("❌ Lỗi: Chỉ có thể resume (--run <id>) mới dùng được `--from`.")
                        return 2
                    if not args.query:
                        print("❌ `run` từ đầu cần --query (phase ingest).")
                        return 2
                    if not args.protocol or not args.protocol.exists():
                        print("❌ Lỗi: Khởi tạo run mới yêu cầu --protocol (file JSON hợp lệ).")
                        return 2
                        
                    hex_part = f"{random.randint(0, 0xffff):04x}"
                    run_id = f"sr-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{hex_part}"
                    protocol_sha256 = get_sha256(args.protocol)
                    created_at = datetime.now(timezone.utc).isoformat()
                    
                    store.conn.execute(
                        """INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256, state, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (run_id, args.query, str(args.protocol), protocol_sha256, "OPEN", created_at)
                    )
                    store.conn.commit()
                    print(f"🚀 Bắt đầu run mới: {run_id}")
                    os.environ["SR_RUN_ID"] = run_id

                return run_pipeline(store, phases, args, start_from=args.start_from)
            finally:
                writer_lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
