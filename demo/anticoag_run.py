"""Chạy thử SR-Agent trên chủ đề y khoa đầu tiên: quản lý chống đông chu phẫu.

Khác demo/rag_demo.py ở chỗ: KHÔNG đọc seed JSON đã dọn sẵn, mà đẩy XML efetch
thô qua ĐÚNG PubMedFetcher.parse_efetch_xml() thật. Nghĩa là đường đi mã nguồn
được kiểm ở đây là đường đi thật khi có mạng, chỉ thay tầng vận chuyển HTTP.

    python3 demo/anticoag_run.py

Trên máy có mạng, bản thật là:
    python3 -c "from tools.sources.pubmed import PubMedFetcher; \
                print(PubMedFetcher().search('perioperative anticoagulation', 20))"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sr_agent.models.schemas import Document
from sr_agent.pipeline import Pipeline
from sr_agent.store.staging import StagingStore
from tools.guard.firewall import check_output
from tools.sources.medical_router import MedicalSourceRouter
from tools.sources.pubmed import PubMedFetcher

XML_PATH = ROOT / "demo" / "anticoag_efetch.xml"
DB_PATH = ROOT / "staging" / "demo_anticoag.db"
QUERY = "perioperative anticoagulation management"
MEDICAL_RUBRIC = json.loads(
    (ROOT / "tools" / "profiles" / "medical.json").read_text(encoding="utf-8")
)


class OfflinePubMedFetcher(PubMedFetcher):
    """PubMedFetcher với tầng HTTP thay bằng file XML — parser thật giữ nguyên."""

    def __init__(self, xml_text: str):
        super().__init__(client=None)
        self._docs = self.parse_efetch_xml(xml_text)

    def search(self, query: str, max_results: int = 20) -> list[str]:
        return [d.source_id for d in self._docs[:max_results]]

    def fetch(self, source_ids) -> list[Document]:
        wanted = set(source_ids)
        # Duyệt _docs MỘT lần (không phải tích Descartes theo source_ids) để bản
        # ghi lặp PMID xuất hiện đúng số lần có trong XML — tầng 1 chống trùng
        # cần thấy đúng 2 bản, không phải 4.
        return [d for d in self._docs if d.source_id in wanted]


def _rejected(store: StagingStore):
    """Đọc thẳng bản ghi bị loại từ SQLite — store chưa có API lọc theo status."""
    rows = store.conn.execute(
        "SELECT uid, payload FROM documents WHERE status = 'rejected'"
    ).fetchall()
    out = []
    for uid, payload in rows:
        d = json.loads(payload)
        out.append((uid, (d.get("rubric") or {}).get("total", 0.0),
                    d.get("evidence_level"), d.get("title", "")))
    return sorted(out, key=lambda r: -r[1])


def banner(text: str) -> None:
    print(f"\n{'=' * 66}\n{text}\n{'=' * 66}")


def main() -> int:
    banner("GĐ1 — Nạp & phân tích XML PubMed qua parser thật")
    fetcher = OfflinePubMedFetcher(XML_PATH.read_text(encoding="utf-8"))
    print(f"Bản ghi phân tích được : {len(fetcher._docs)}")
    for d in fetcher._docs:
        lvl = fetcher.evidence_levels.get(d.uid)
        types = ", ".join(fetcher.publication_types.get(d.uid, [])) or "—"
        print(f"  {d.uid:<18} bậc CC={str(lvl):<5} [{types}]")
        print(f"      {d.title[:78]}")

    banner("GĐ2 — Định tuyến (router y khoa, lõi không đổi)")
    router = MedicalSourceRouter(fetchers={"pubmed": fetcher})
    for raw in ["pmid:26095867", "arxiv:2401.12345", "10787654"]:
        print(f"  {raw:<22} -> {router.classify(raw)}")

    banner("GĐ3 — Chạy pipeline thật, ĐỐI CHỨNG 2 rubric")
    results: dict[str, tuple] = {}
    for nhan, profile in (("CS (mặc định)", None), ("Y KHOA (mới)", MEDICAL_RUBRIC)):
        db = DB_PATH.with_name(f"demo_anticoag_{'cs' if profile is None else 'med'}.db")
        if db.exists():
            db.unlink()
        store = StagingStore(db)
        fetcher._docs = OfflinePubMedFetcher(
            XML_PATH.read_text(encoding="utf-8"))._docs
        report = Pipeline(store=store, router=MedicalSourceRouter(
            fetchers={"pubmed": fetcher}), rubric=profile).run(QUERY, max_results=20)
        results[nhan] = (report, store)

    print(f"  {'chỉ số':<20} {'CS (mặc định)':>16} {'Y KHOA (mới)':>16}")
    for f in ("fetched", "new", "duplicates", "rejected_by_rubric", "queued", "dlq"):
        a = getattr(results["CS (mặc định)"][0], f)
        b = getattr(results["Y KHOA (mới)"][0], f)
        print(f"  {f:<20} {a:>16} {b:>16}")

    banner("GĐ4 — Hàng đợi duyệt: rubric nào xếp đúng?")
    for nhan, (_, store) in results.items():
        print(f"\n  --- {nhan} ---")
        rows = store.get_wip_queue()
        if not rows:
            print("    (rỗng)")
        for i, d in enumerate(rows, 1):
            score = d.rubric.total if d.rubric else 0.0
            lvl = d.evidence_level
            print(f"    {i}. {score:6.2f}  bậcCC={str(lvl):<4} {d.title[:52]}")
        for uid, total, lvl, title in _rejected(store):
            print(f"    ✗ LOẠI {total:6.2f}  bậcCC={str(lvl):<4} {title[:48]}")

    banner("GĐ5 — Firewall lâm sàng trên bản thảo tổng hợp")
    sources = [d.abstract or "" for d in fetcher._docs]

    trung_thuc = ("Bắc cầu bằng heparin trọng lượng phân tử thấp không vượt trội "
                  "so với không bắc cầu, và làm tăng chảy máu nặng. Phân tích gộp "
                  "trên 1847 bệnh nhân van tim cơ học không thấy lợi ích huyết khối rõ rệt.")
    bia_dat = ("Bắc cầu bằng heparin nên ngưng 36 giờ trước tê tủy sống và dùng "
               "liều 40 mg mỗi 12 giờ, giữ INR dưới 1.8.")

    for nhan, text in (("TRUNG THỰC", trung_thuc), ("BỊA ĐẶT", bia_dat)):
        v = check_output(text, sources, domain="clinical")
        ket = "ĐI QUA" if v.passed else "BỊ CHẶN"
        print(f"\n  [{nhan}] -> {ket}  (mỏ neo kiểm: {v.anchors_checked})")
        for viol in v.violations:
            print(f"      ✗ {viol.anchor.raw!r} ({viol.anchor.kind}) không có trong nguồn")

    banner("KẾT THÚC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
