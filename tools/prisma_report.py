"""PRISMA Report Generator.

Computes and prints the PRISMA 2020 flowchart based on staging DB events and records.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore

logger = logging.getLogger("tools.prisma_report")


# --- Số đo của sơ đồ, kèm trạng thái VÔ HIỆU (luật L3) ---------------------------------
#
# Trước đây ba bộ đếm dưới đây hỏi `events` bằng những TÊN KHÔNG AI GHI:
#   hỏi 'FETCHED' · 'DUPLICATE_ID' · 'DUPLICATE_FUZZY' · 'REJECTED'+detail LIKE '%rubric%'
#   pipeline ghi 'DEDUP_DROPPED' · 'DEDUP_MERGED' · 'RUBRIC_REJECTED'
# Giao của hai tập là RỖNG, nên mọi nhánh dự phòng luôn trả 0. Nhánh chính (đọc
# runs.report_json) thì chạy đúng, nên lỗi này bị che: hễ có bản ghi `runs` là số ra đúng.
# Chỗ chết người là khi KHÔNG có `runs` — báo cáo in ra 0 và "0 bản trùng bị loại" trông
# y hệt "chưa ai đo bản trùng".

class SoDo:
    """Một con số của sơ đồ. `vo_hieu=True` nghĩa là KHÔNG ĐO ĐƯỢC, khác hẳn giá trị 0."""

    def __init__(self, gia_tri: int | None, nguon: str, ghi_chu: str = "") -> None:
        self.gia_tri = gia_tri
        self.nguon = nguon
        self.ghi_chu = ghi_chu

    @property
    def vo_hieu(self) -> bool:
        return self.gia_tri is None

    def __str__(self) -> str:
        if self.vo_hieu:
            return f"VÔ HIỆU (không đo được — {self.ghi_chu})"
        return f"{self.gia_tri}" + (f"  [{self.ghi_chu}]" if self.ghi_chu else "")

    def cho_so_do(self) -> str:
        """Nhãn ngắn dùng trong sơ đồ mermaid."""
        return "VÔ HIỆU" if self.vo_hieu else str(self.gia_tri)


def _tong_tu_runs(conn, khoa: str) -> tuple[int, int]:
    """Cộng một khoá qua mọi bản ghi `runs`. Trả (tổng, số lần chạy CÓ khai khoá đó).

    Số thứ hai mới là thứ phân biệt "đo được và bằng 0" với "chưa ai đo".
    """
    tong = 0
    so_lan = 0
    for row in conn.execute("SELECT report_json FROM runs"):
        try:
            report = json.loads(row["report_json"])
        except Exception:
            continue
        if khoa in report:
            tong += int(report.get(khoa) or 0)
            so_lan += 1
    return tong, so_lan


def _dem_su_kien(conn, ten: tuple[str, ...]) -> int:
    cho = ",".join("?" for _ in ten)
    return conn.execute(
        f"SELECT COUNT(*) n FROM events WHERE event_type IN ({cho})", ten
    ).fetchone()["n"]


def generate_prisma_report(store: StagingStore) -> str:
    conn = store.conn

    # 1. Identification
    tong, so_lan = _tong_tu_runs(conn, "fetched")
    if so_lan:
        identified = SoDo(tong, "runs.report_json", f"{so_lan} lần chạy")
    else:
        identified = SoDo(
            None, "—",
            "không lần chạy nào ghi 'fetched', và không nơi nào trong kho ghi sự kiện FETCHED",
        )

    # Duplicates — nhánh dự phòng đếm ĐÚNG tên pipeline đang ghi.
    tong, so_lan = _tong_tu_runs(conn, "duplicates")
    if so_lan:
        duplicates_removed = SoDo(tong, "runs.report_json", f"{so_lan} lần chạy")
    else:
        n = _dem_su_kien(conn, ("DEDUP_DROPPED", "DEDUP_MERGED"))
        if n:
            # pipeline.py:83-85 nhánh DUPLICATE_ID thoát ra KHÔNG ghi sự kiện nào, mà
            # pipeline.py nằm trong vùng cấm L2 nên không sửa được từ đây. Vậy con số
            # này là SÀN, không phải tổng.
            duplicates_removed = SoDo(n, "events", "SÀN — trùng tầng 1 không được ghi sự kiện")
        else:
            duplicates_removed = SoDo(
                None, "—", "không có lần chạy nào và không có sự kiện dedup nào",
            )

    # Rubric rejected
    tong, so_lan = _tong_tu_runs(conn, "rejected_by_rubric")
    if so_lan:
        rubric_rejected = SoDo(tong, "runs.report_json", f"{so_lan} lần chạy")
    else:
        n = _dem_su_kien(conn, ("RUBRIC_REJECTED",))
        if not n:
            n = conn.execute(
                "SELECT COUNT(*) n FROM documents WHERE status = 'rejected' "
                "AND uid NOT IN (SELECT DISTINCT uid FROM screening)"
            ).fetchone()["n"]
            nguon = "documents.status"
        else:
            nguon = "events"
        rubric_rejected = SoDo(n, nguon) if n else SoDo(
            None, "—", "không lần chạy, không sự kiện RUBRIC_REJECTED, không bản ghi bị loại",
        )

    # 2. Screening
    # Screened: documents that have screening verdicts
    screened = conn.execute("SELECT COUNT(DISTINCT uid) n FROM screening").fetchone()["n"]
    
    # Excluded by screening:
    # Let's count unique uids where verdict is 'exclude'
    excluded = conn.execute(
        "SELECT COUNT(DISTINCT uid) n FROM screening WHERE verdict = 'exclude'"
    ).fetchone()["n"]
    
    # Excluded reasons
    exclusion_reasons = {}
    for r in conn.execute(
        "SELECT criterion_id, COUNT(DISTINCT uid) n FROM screening WHERE verdict = 'exclude' GROUP BY criterion_id"
    ):
        cid = r["criterion_id"] or "Unknown"
        exclusion_reasons[cid] = r["n"]
        
    # 3. Eligibility (full-text)
    # Assessed for eligibility: documents that passed screening (agreement on include, or resolved by tiebreaker)
    # For Phase M6a: any screened document with verdict='include'
    # For future: we can check documents that passed screening.
    # Let's count uids that are not excluded by screening and did not fail rubric
    eligible = screened - excluded
    
    # Excluded at eligibility (full-text): e.g. EF1..EF4.
    # In Phase M6a, this is 0 since we haven't done full-text eligibility screening.
    full_text_excluded = 0
    full_text_reasons = {}
    
    # 4. Included
    # Included: status = APPROVED or APPROVED_LOCAL
    included = conn.execute(
        "SELECT COUNT(*) n FROM documents WHERE status IN ('approved', 'approved_local')"
    ).fetchone()["n"]
    
    # Abstract-only: count of queued/approved documents that do not have full_text in payload
    abstract_only = 0
    for row in conn.execute("SELECT payload FROM documents WHERE status IN ('queued', 'approved', 'approved_local')"):
        try:
            doc = Document.model_validate_json(row["payload"])
            if not doc.full_text or not doc.full_text.strip():
                abstract_only += 1
        except Exception:
            pass
            
    # Format report
    report_lines = [
        "# PRISMA 2020 Flow Diagram",
        "",
        "## 1. Identification",
        f"- **Records identified from databases**: {identified}",
        f"- **Duplicate records removed**: {duplicates_removed}",
        f"- **Records excluded by quality gate (rubric < 60)**: {rubric_rejected}",
        "",
        "## 2. Screening (Title/Abstract)",
        f"- **Records screened**: {screened}",
        f"- **Records excluded**: {excluded}",
    ]
    
    if exclusion_reasons:
        for cid, count in sorted(exclusion_reasons.items()):
            report_lines.append(f"  - **{cid}**: {count} records")
            
    report_lines.extend([
        "",
        "## 3. Eligibility (Full-Text)",
        f"- **Full-text articles assessed for eligibility**: {eligible}",
        f"- **Full-text articles excluded with reasons**: {full_text_excluded}",
    ])
    
    if full_text_reasons:
        for cid, count in sorted(full_text_reasons.items()):
            report_lines.append(f"  - **{cid}**: {count} records")
            
    report_lines.extend([
        f"  - **Abstract-only (no full-text retrieved)**: {abstract_only}",
        "",
        "## 4. Inclusion",
        f"- **Studies included in systematic review**: {included}",
        "",
        "```mermaid",
        "flowchart TD",
        f"    ID[Identified: {identified.cho_so_do()} records] --> "
        f"DUP[Duplicates Removed: {duplicates_removed.cho_so_do()} records]",
        f"    DUP --> RUB[Quality Gate Excluded: {rubric_rejected.cho_so_do()} records]",
        f"    DUP --> SCR[Screened: {screened} records]",
        f"    SCR --> EXC[Screening Excluded: {excluded} records]",
        f"    SCR --> ELG[Eligible: {eligible} records]",
        f"    ELG --> ABS[Abstract-only: {abstract_only} records]",
        f"    ELG --> INC[Included Studies: {included} records]",
        "```"
    ])
    
    return "\n".join(report_lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PRISMA Flowchart Report Generator")
    ap.add_argument("--db", type=Path, help="Override DB path (SQLite)")
    args = ap.parse_args(argv)
    
    store_path = args.db if args.db else None
    with StagingStore(store_path) if store_path else StagingStore() as store:
        report = generate_prisma_report(store)
        print(report)
        
    return 0


if __name__ == "__main__":
    sys.exit(main())
