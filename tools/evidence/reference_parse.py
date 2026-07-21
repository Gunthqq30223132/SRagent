"""Parser .ris / .bib → RefRecord (M8 Result A). Tất định 100%, local, không dep mới.

Nguồn chọn bởi NGƯỜI: export .ris/.bib từ giao diện PubMed/Embase/Europe PMC/IEEE/arXiv
rồi thả vào thư mục — hệ chỉ parse, không tự quyết nguồn (D33 §2). Parser viết tay có
chủ đích (cấm dep mới): phủ tập tag/trường thực dụng của 5 nguồn đích, KHÔNG nhận là
parser tổng quát cho mọi biến thể RIS/BibTeX tồn tại.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.evidence.schemas import RefRecord

# --- RIS ----------------------------------------------------------------------------

_RIS_TAG_RE = re.compile(r"^([A-Z][A-Z0-9])  - ?(.*)$")

# Map tag RIS → trường RefRecord (tag lạ được bỏ qua, không lỗi).
_RIS_TITLE_TAGS = ("TI", "T1")
_RIS_ABSTRACT_TAGS = ("AB", "N2")
_RIS_VENUE_TAGS = ("JO", "JF", "T2")


def _finish_ris_record(fields: dict, source_db: str, provenance: str) -> RefRecord | None:
    title = next((fields[t] for t in _RIS_TITLE_TAGS if fields.get(t)), None)
    if not title:
        return None
    ids: dict[str, str] = {}
    if fields.get("DO"):
        ids["doi"] = fields["DO"].strip()
    # PubMed export để PMID trong AN hoặc ID; chỉ nhận khi thuần chữ số.
    for tag in ("AN", "ID"):
        v = (fields.get(tag) or "").strip()
        if v.isdigit():
            ids.setdefault("pmid", v)
    year = None
    py = (fields.get("PY") or fields.get("Y1") or "").strip()
    m = re.match(r"(\d{4})", py)
    if m:
        year = int(m.group(1))
    return RefRecord(
        source_db=source_db,
        external_ids=ids,
        title=title.strip(),
        authors=fields.get("_authors", []),
        year=year,
        venue=next((fields[t] for t in _RIS_VENUE_TAGS if fields.get(t)), None),
        abstract=next((fields[t] for t in _RIS_ABSTRACT_TAGS if fields.get(t)), None),
        raw_type=fields.get("TY"),
        provenance=provenance,
    )


def parse_ris(path: str, source_db: str) -> list[RefRecord]:
    """Parse một file .ris; mỗi record kết thúc bằng 'ER  -'. Record thiếu title bị bỏ
    qua (đếm được qua chênh lệch), không làm hỏng batch — cô lập lỗi từng bản ghi."""
    text = Path(path).read_text(encoding="utf-8-sig")
    records: list[RefRecord] = []
    fields: dict = {"_authors": []}
    idx = 0
    last_tag: str | None = None
    for line in text.splitlines():
        m = _RIS_TAG_RE.match(line)
        if not m:
            # dòng nối dài của tag trước (AB nhiều dòng)
            if last_tag and last_tag in fields and line.strip():
                fields[last_tag] += " " + line.strip()
            continue
        tag, value = m.group(1), m.group(2).strip()
        if tag == "ER":
            rec = _finish_ris_record(fields, source_db, f"{path}#{idx}")
            if rec:
                records.append(rec)
            idx += 1
            fields = {"_authors": []}
            last_tag = None
            continue
        if tag == "AU":
            fields["_authors"].append(value)
        elif tag not in fields:      # RIS lặp tag → giữ giá trị đầu (tất định)
            fields[tag] = value
        last_tag = tag if tag != "AU" else None
    return records


# --- BibTeX ---------------------------------------------------------------------------

_BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)


def _parse_bib_fields(body: str) -> dict[str, str]:
    """Bóc field = {value}/"value" với đếm ngoặc — đủ cho export chuẩn của arXiv/IEEE."""
    fields: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        m = re.compile(r"(\w+)\s*=\s*", re.IGNORECASE).search(body, i)
        if not m:
            break
        name = m.group(1).casefold()
        j = m.end()
        if j < n and body[j] == "{":
            depth, k = 1, j + 1
            while k < n and depth:
                depth += body[k] == "{"
                depth -= body[k] == "}"
                k += 1
            fields[name] = body[j + 1:k - 1].strip()
            i = k
        elif j < n and body[j] == '"':
            k = body.find('"', j + 1)
            k = n if k == -1 else k
            fields[name] = body[j + 1:k].strip()
            i = k + 1
        else:
            k = body.find(",", j)
            k = n if k == -1 else k
            fields[name] = body[j:k].strip()
            i = k
    return fields


def parse_bibtex(path: str, source_db: str) -> list[RefRecord]:
    text = Path(path).read_text(encoding="utf-8-sig")
    records: list[RefRecord] = []
    for idx, m in enumerate(_BIB_ENTRY_RE.finditer(text)):
        start = m.end()
        nxt = _BIB_ENTRY_RE.search(text, start)
        body = text[start:nxt.start()] if nxt else text[start:]
        f = _parse_bib_fields(body)
        title = re.sub(r"[{}]", "", f.get("title", "")).strip()
        if not title:
            continue
        ids: dict[str, str] = {}
        if f.get("doi"):
            ids["doi"] = f["doi"].strip()
        eprint = f.get("eprint", "").strip()
        if eprint and re.match(r"^\d{4}\.\d{4,5}", eprint):
            ids["arxiv"] = f"arxiv:{eprint}"
        year = None
        ym = re.match(r"(\d{4})", f.get("year", ""))
        if ym:
            year = int(ym.group(1))
        authors = [a.strip() for a in re.split(r"\s+and\s+", f.get("author", "")) if a.strip()]
        records.append(RefRecord(
            source_db=source_db,
            external_ids=ids,
            title=title,
            authors=authors,
            year=year,
            venue=f.get("journal") or f.get("booktitle"),
            abstract=f.get("abstract"),
            raw_type=m.group(1).casefold(),
            provenance=f"{path}#{idx}",
        ))
    return records


def parse_directory(dir_path: str, source_map: dict[str, str]) -> list[RefRecord]:
    """Quét thư mục export: source_map = {tên file (hoặc prefix): source_db}.
    File không khai trong map → source_db='unknown' tier thấp nhất, KHÔNG đoán nguồn."""
    out: list[RefRecord] = []
    for p in sorted(Path(dir_path).iterdir()):
        if p.suffix.lower() not in {".ris", ".bib"}:
            continue
        source = next(
            (db for prefix, db in sorted(source_map.items()) if p.name.startswith(prefix)),
            "unknown",
        )
        parser = parse_ris if p.suffix.lower() == ".ris" else parse_bibtex
        out.extend(parser(str(p), source))
    return out
