"""NotebookLMExporter — ĐƯỜNG EXPORT thủ công, KHÔNG phải provider (phán quyết D31 #7).

NotebookLM không có API; ép nó vào interface provider là abstraction giả. Thay vào
đó nó là một EXPORTER: gom các nguồn Layer A đã chọn thành một bundle Markdown đã
`sanitize` để NGƯỜI tự upload; kết quả NotebookLM quay về hệ qua đường thủ công +
firewall §4 khi trích số liệu.

Bất biến an toàn: MỌI file trong bundle phải qua outbound.scan() = 0 findings TRƯỚC
khi ghi bất kỳ byte nào ra đĩa. Có finding ⇒ fail-closed: không tạo thư mục, không
ghi file nào (không rò rỉ một phần). Module ngoài core, CHỈ IMPORT tools/guard/.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))  # chạy được khi chưa pip install -e

from sr_agent.models.schemas import Document
from sr_agent.store.staging import StagingStore
from tools.guard.outbound import OutboundViolation, scan

DEFAULT_EXPORTS_ROOT = ROOT / "staging" / "exports"


class ExporterError(Exception):
    """Bundle không dựng được (uid thiếu, input rỗng)."""


# --- Render (tất định, offline — không LLM) -----------------------------------


def _safe_stem(uid: str) -> str:
    """uid → tên file an toàn: bỏ ký tự phân tách đường dẫn, giữ phần còn lại."""
    return uid.replace(":", "_").replace("/", "_").replace("\\", "_")


def _year(doc: Document) -> str:
    return str(doc.published_date.year) if doc.published_date else "n/a"


def _one_line_summary(doc: Document) -> str:
    """1 câu tóm tắt tất định: câu đầu của abstract, fallback về title."""
    if doc.abstract:
        first = doc.abstract.strip().split(". ", 1)[0].strip()
        return (first[:200] + "…") if len(first) > 200 else first
    return doc.title.strip()


def _render_source_md(doc: Document) -> str:
    lines = [
        f"# {doc.title}",
        "",
        f"- **uid**: {doc.uid}",
        f"- **source**: {doc.source}",
        f"- **authority_tier**: {doc.authority_tier}",
        f"- **year**: {_year(doc)}",
    ]
    if doc.authors:
        lines.append(f"- **authors**: {', '.join(doc.authors)}")
    if doc.url:
        lines.append(f"- **url**: {doc.url}")
    lines += ["", "## Nội dung nguồn (canonical)", ""]
    lines.append(doc.full_text or doc.abstract or "(không có nội dung văn bản)")
    return "\n".join(lines) + "\n"


def _render_source_map(docs: list[Document]) -> str:
    lines = [
        "# SOURCE_MAP",
        "",
        "Bản đồ nguồn cho NotebookLM (mỗi dòng: uid · title · year · tóm tắt).",
        "",
        "| uid | title | year | tóm tắt |",
        "| --- | --- | --- | --- |",
    ]
    for doc in docs:
        title = doc.title.replace("|", "\\|")
        summary = _one_line_summary(doc).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {doc.uid} | {title} | {_year(doc)} | {summary} |")
    return "\n".join(lines) + "\n"


def _render_questions(docs: list[Document], question: str | None) -> str:
    lines = ["# Câu hỏi gợi ý cho NotebookLM", ""]
    if question:
        lines += [f"## Câu hỏi trọng tâm", "", f"- {question}", ""]
    lines += ["## Câu hỏi phản biện (sinh lúc parse)", ""]
    seen: set[str] = set()
    for doc in docs:
        for cq in doc.critique_questions:
            q = cq.question.strip()
            if q and q not in seen:
                seen.add(q)
                lines.append(f"- {q}  _(nguồn: {doc.uid})_")
    if not seen:
        lines += [
            "- Các nguồn này đồng thuận và mâu thuẫn ở điểm nào?",
            "- Bằng chứng thực nghiệm nào còn thiếu để trả lời câu hỏi trọng tâm?",
        ]
    return "\n".join(lines) + "\n"


def _render_readme(docs: list[Document], ts: str) -> str:
    return (
        "# Bundle NotebookLM (export thủ công)\n"
        "\n"
        f"- Tạo lúc: {ts}\n"
        f"- Số nguồn: {len(docs)}\n"
        "\n"
        "NotebookLM KHÔNG có API — đây là đường export thủ công (phán quyết D31 #7).\n"
        "\n"
        "## Cách dùng\n"
        "1. Mở NotebookLM, tạo notebook mới.\n"
        "2. Upload từng file `*.md` nguồn trong thư mục này làm Source.\n"
        "3. Dùng `SOURCE_MAP.md` để đối chiếu uid ↔ nguồn.\n"
        "4. Đặt câu hỏi theo `QUESTIONS.md`.\n"
        "5. Khi mang số liệu từ NotebookLM về hệ, cho qua Numeric Firewall (§4) trước.\n"
        "\n"
        "Mọi file đã qua Outbound Interceptor (outbound.scan = 0 findings) trước khi ghi.\n"
    )


# --- API ----------------------------------------------------------------------


def build_bundle(
    doc_uids: list[str],
    db_path: str | Path,
    *,
    exports_root: str | Path | None = None,
    question: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Dựng bundle NotebookLM cho các uid đã chọn → thư mục staging/exports/<ts>-notebooklm/.

    Trả về đường dẫn thư mục bundle. Fail-closed: nếu BẤT KỲ file nào có finding
    outbound thì raise OutboundViolation và KHÔNG ghi gì ra đĩa.
    """
    if not doc_uids:
        raise ExporterError("build_bundle cần ít nhất một doc_uid.")

    with StagingStore(db_path) as store:
        docs: list[Document] = []
        missing: list[str] = []
        for uid in doc_uids:
            doc = store.get(uid)
            if doc is None:
                missing.append(uid)
            else:
                docs.append(doc)
    if missing:
        raise ExporterError(f"uid không có trong store: {missing}")

    # 1) Dựng toàn bộ nội dung trong RAM trước.
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    files: dict[str, str] = {"README.md": _render_readme(docs, ts)}
    for doc in docs:
        files[f"{_safe_stem(doc.uid)}.md"] = _render_source_md(doc)
    files["SOURCE_MAP.md"] = _render_source_map(docs)
    files["QUESTIONS.md"] = _render_questions(docs, question)

    # 2) Chốt outbound TRƯỚC khi ghi: quét MỌI file, gom finding, chặn nếu có.
    findings = []
    for content in files.values():
        findings.extend(scan(content))
    if findings:
        raise OutboundViolation(findings)  # fail-closed: chưa tạo thư mục nào

    # 3) Sạch → ghi bundle.
    bundle_dir = Path(exports_root or DEFAULT_EXPORTS_ROOT) / f"{ts}-notebooklm"
    bundle_dir.mkdir(parents=True, exist_ok=False)
    for fname, content in files.items():
        (bundle_dir / fname).write_text(content, encoding="utf-8")
    return bundle_dir


# --- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dựng bundle NotebookLM (export thủ công) cho các uid đã chọn."
    )
    parser.add_argument("--uids", nargs="+", required=True, help="uid nguồn cần export")
    parser.add_argument("--db", required=True, help="đường dẫn staging DB")
    parser.add_argument("--question", default=None, help="câu hỏi trọng tâm (tùy chọn)")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        bundle = build_bundle(args.uids, args.db, question=args.question)
    except OutboundViolation as exc:
        print(f"BỊ CHẶN — bundle chứa nội dung nhạy cảm: {exc}", file=sys.stderr)
        return 1
    except ExporterError as exc:
        print(f"LỖI — {exc}", file=sys.stderr)
        return 2
    print(f"Bundle sẵn sàng để upload thủ công: {bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
