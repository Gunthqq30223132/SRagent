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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sr_agent.models.schemas import DocStatus  # noqa: E402
from sr_agent.store.staging import StagingStore  # noqa: E402

# Trạng thái "hậu cổng người": sự tồn tại của bất kỳ doc nào ở đây = người ĐÃ
# ra ít nhất một quyết định duyệt. Orchestrator chỉ đọc, không tạo.
_APPROVED_STATES = (DocStatus.APPROVED.value, DocStatus.APPROVED_LOCAL.value)

AUTO = "auto"
HUMAN_GATE = "human_gate"


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
            name="extract",
            kind=AUTO,
            desc="Trích dữ liệu có thuế bằng chứng (evidenced extraction).",
            runner_ref=("tools.evidence_extract", "main"),
            build_args=lambda a: ["--limit", str(a.limit)],
        ),
        Phase(
            name="rob",
            kind=AUTO,
            desc="Đánh giá Risk-of-Bias (BS3) — hạ trọng số study thiên lệch.",
            runner_ref=("tools.rob_run", "main"),
            build_args=lambda a: ["--protocol", str(a.protocol), "--limit", str(a.limit)],
        ),
        Phase(
            name="consensus_review",
            kind=HUMAN_GATE,
            desc="CON NGƯỜI xác nhận tập bằng chứng trước khi tổng hợp (BS4). "
            "Cổng người thứ hai — không tự vượt.",
            satisfied=lambda store: False,  # v1: luôn dừng — tổng hợp chưa nối
            resume_hint="consensus",
        ),
        Phase(
            name="consensus",
            kind=AUTO,
            desc="Tổng hợp đồng thuận + firewall số (BS4).",
            runner_ref=("tools.consensus_run", "main"),
            build_args=lambda a: ["--protocol", str(a.protocol)],
        ),
    ]


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


def cmd_status(store: StagingStore, phases: list[Phase]) -> int:
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

    run_p = sub.add_parser("run", help="chạy tuyến, dừng ở cổng người chưa thỏa")
    run_p.add_argument("--query", default="", help="truy vấn ingest (phase đầu)")
    run_p.add_argument("--max-results", type=int, default=20)
    run_p.add_argument("--protocol", type=Path, help="protocol JSON cho screen/eligibility/rob")
    run_p.add_argument("--limit", type=int, default=10)
    run_p.add_argument("--from", dest="start_from", default=None,
                       help="tiếp tục từ phase này (sau khi đã duyệt)")
    run_p.add_argument("--db", type=Path, help="override DB path")

    args = ap.parse_args(argv)
    phases = build_phases()

    if args.cmd == "plan":
        return cmd_plan(phases)

    db_kwargs = {"db_path": args.db} if getattr(args, "db", None) else {}
    with StagingStore(**db_kwargs) as store:
        if args.cmd == "status":
            return cmd_status(store, phases)
        if args.cmd == "run":
            if args.start_from is None and not args.query:
                print("❌ `run` từ đầu cần --query (phase ingest). "
                      "Hoặc dùng --from <phase> để tiếp tục.")
                return 2
            return run_pipeline(store, phases, args, start_from=args.start_from)
    return 0


if __name__ == "__main__":
    sys.exit(main())
