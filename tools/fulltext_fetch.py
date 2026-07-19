"""Full-Text Acquisition Tool — D38 Full-Text Acquisition Ladder.

Tầng thử nghiệm 4 bậc (rungs 1-4) theo thứ tự:
1. arXiv PDF (source=arxiv)
2. Europe PMC OA XML (source=europepmc AND is_open_access)
3. Warehouse lookup (all sources; title_normalized match)
4. Inbox thủ công (all sources; staging/fulltext_inbox/<uid_with_underscores>.pdf)

Thang thử lần lượt 1->2->3->4 và DỪNG ở bậc đầu tiên thành công.
Ghi nhận provenance detail: `rung=<n> source=<...> chars=<len>`.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Sequence

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools.warehouse.config import WAREHOUSE_DB_PATH
from tools.warehouse.ingest_pdf import extract_text_from_pdf
from tools.warehouse.read_doc import get_document_text

logger = logging.getLogger("tools.fulltext_fetch")

MIN_FULLTEXT_LENGTH = 2000

_EPMC_CANON_RE = re.compile(r"^europepmc:(MED|PMC|PPR):(\d+)$", re.IGNORECASE)


def _split_epmc_id(source_id: str) -> tuple[str, str]:
    m = _EPMC_CANON_RE.match(source_id)
    if m:
        return m.group(1).upper(), m.group(2)
    parts = source_id.split(":")
    if len(parts) >= 3:
        return parts[1].upper(), parts[2]
    return "MED", source_id


def _get_jats_element_text(elem: ET.Element) -> str:
    tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
    if tag_name.lower() in ("ref-list", "ref", "back", "front"):
        return ""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        child_text = _get_jats_element_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            parts.append(child.tail)
    return " ".join(parts)


def parse_jats_xml_body(xml_str: str | bytes) -> str:
    """Parses JATS XML body text using xml.etree stdlib, skipping reference lists."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML: {exc}") from exc

    body = None
    for elem in root.iter():
        tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag_name.lower() == "body":
            body = elem
            break

    target = body if body is not None else root
    raw_text = _get_jats_element_text(target)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return "\n\n".join(lines)


def is_doc_open_access(doc: Document) -> bool:
    if getattr(doc, "is_open_access", False):
        return True
    if getattr(doc, "isOpenAccess", None) in ("Y", True, "true", "True"):
        return True
    return False


def fetch_fulltext_batch(
    store: StagingStore,
    limit: int = 10,
    client: Optional[httpx.Client] = None,
    rungs: Sequence[int] | str | None = None,
    warehouse_db_path: Path | None = None,
    inbox_dir: Path | None = None,
) -> int:
    """Fetches full-text for docs queued with SCREEN_INCLUDED and missing full_text using the 4-rung ladder."""
    if rungs is None:
        active_rungs = [1, 2, 3, 4]
    elif isinstance(rungs, str):
        active_rungs = [int(r.strip()) for r in rungs.split(",") if r.strip().isdigit()]
    else:
        active_rungs = list(rungs)

    wh_path = warehouse_db_path or WAREHOUSE_DB_PATH
    inbox_base = inbox_dir or (ROOT / "staging" / "fulltext_inbox")

    rows = store.conn.execute(
        """
        SELECT uid FROM documents
        WHERE status = ?
          AND uid IN (SELECT uid FROM events WHERE event_type = 'SCREEN_INCLUDED')
          AND (json_extract(payload, '$.full_text') IS NULL OR json_extract(payload, '$.full_text') = '')
        """,
        (DocStatus.QUEUED.value,),
    ).fetchall()

    to_process = [r["uid"] for r in rows]
    if not to_process:
        print("No documents require full-text acquisition.")
        return 0

    own_client = False
    if client is None:
        client = httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "SR-Agent/1.0 (academic literature pipeline)"},
        )
        own_client = True

    processed_count = 0

    try:
        for uid in to_process[:limit]:
            doc = store.get(uid)
            if not doc:
                continue

            success = False

            for rung in active_rungs:
                if success:
                    break

                # --- Rung 1: arXiv PDF ---
                if rung == 1:
                    if doc.source != "arxiv":
                        continue

                    raw_id = doc.source_id or uid
                    arxiv_id = raw_id.split("arxiv:", 1)[1] if "arxiv:" in raw_id else raw_id
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    print(f"[Rung 1] Fetching arXiv PDF: {uid} ({pdf_url})")

                    tmp_path = None
                    try:
                        resp = client.get(pdf_url)
                        if resp.status_code != 200:
                            store.log_event(
                                uid,
                                "FULLTEXT_FETCH_FAILED",
                                f"rung=1 source=arxiv_pdf error=HTTP {resp.status_code}",
                            )
                            continue

                        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                            tmp.write(resp.content)
                            tmp_path = tmp.name

                        text = extract_text_from_pdf(tmp_path)
                        text_clean = text.strip() if text else ""

                        if len(text_clean) >= MIN_FULLTEXT_LENGTH:
                            doc.full_text = text
                            store.upsert(doc, touch=False)
                            store.log_event(
                                uid,
                                "FULLTEXT_FETCHED",
                                f"rung=1 source=arxiv_pdf chars={len(text_clean)}",
                            )
                            success = True
                        else:
                            store.log_event(
                                uid,
                                "FULLTEXT_TOO_SHORT",
                                f"rung=1 source=arxiv_pdf chars={len(text_clean)}",
                            )
                    except Exception as exc:
                        logger.error(f"[Rung 1] Failed for {uid}: {exc}")
                        store.log_event(uid, "FULLTEXT_FETCH_FAILED", f"rung=1 source=arxiv_pdf error={exc}")
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except OSError:
                                pass

                # --- Rung 2: Europe PMC OA XML ---
                elif rung == 2:
                    if doc.source != "europepmc" or not is_doc_open_access(doc):
                        continue

                    src, num = _split_epmc_id(doc.source_id or uid)
                    xml_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{src}/{num}/fullTextXML"
                    print(f"[Rung 2] Fetching EuropePMC XML: {uid} ({xml_url})")

                    try:
                        resp = client.get(xml_url)
                        if resp.status_code != 200:
                            store.log_event(
                                uid,
                                "FULLTEXT_FETCH_FAILED",
                                f"rung=2 source=europepmc_xml error=HTTP {resp.status_code}",
                            )
                            continue

                        text = parse_jats_xml_body(resp.content)
                        text_clean = text.strip() if text else ""

                        if len(text_clean) >= MIN_FULLTEXT_LENGTH:
                            doc.full_text = text
                            store.upsert(doc, touch=False)
                            store.log_event(
                                uid,
                                "FULLTEXT_FETCHED",
                                f"rung=2 source=europepmc_xml chars={len(text_clean)}",
                            )
                            success = True
                        else:
                            store.log_event(
                                uid,
                                "FULLTEXT_TOO_SHORT",
                                f"rung=2 source=europepmc_xml chars={len(text_clean)}",
                            )
                    except Exception as exc:
                        logger.error(f"[Rung 2] Failed for {uid}: {exc}")
                        store.log_event(uid, "FULLTEXT_FETCH_FAILED", f"rung=2 source=europepmc_xml error={exc}")

                # --- Rung 3: Warehouse ---
                elif rung == 3:
                    print(f"[Rung 3] Checking Warehouse for {uid}: {doc.title_normalized[:50]}")
                    try:
                        wh_text = get_document_text(doc.title_normalized, wh_path)
                        if wh_text is not None:
                            text_clean = wh_text.strip()
                            if len(text_clean) >= MIN_FULLTEXT_LENGTH:
                                doc.full_text = wh_text
                                store.upsert(doc, touch=False)
                                store.log_event(
                                    uid,
                                    "FULLTEXT_FETCHED",
                                    f"rung=3 source=warehouse chars={len(text_clean)}",
                                )
                                success = True
                            else:
                                store.log_event(
                                    uid,
                                    "FULLTEXT_TOO_SHORT",
                                    f"rung=3 source=warehouse chars={len(text_clean)}",
                                )
                        else:
                            store.log_event(
                                uid,
                                "FULLTEXT_FETCH_FAILED",
                                "rung=3 source=warehouse error=no_match_or_ambiguous",
                            )
                    except Exception as exc:
                        logger.error(f"[Rung 3] Failed for {uid}: {exc}")
                        store.log_event(uid, "FULLTEXT_FETCH_FAILED", f"rung=3 source=warehouse error={exc}")

                # --- Rung 4: Inbox ---
                elif rung == 4:
                    inbox_filename = f"{uid.replace(':', '_')}.pdf"
                    inbox_file = inbox_base / inbox_filename
                    print(f"[Rung 4] Checking Inbox for {uid}: {inbox_file}")

                    if inbox_file.exists():
                        try:
                            text = extract_text_from_pdf(str(inbox_file))
                            text_clean = text.strip() if text else ""
                            if len(text_clean) >= MIN_FULLTEXT_LENGTH:
                                doc.full_text = text
                                store.upsert(doc, touch=False)
                                store.log_event(
                                    uid,
                                    "FULLTEXT_FETCHED",
                                    f"rung=4 source=inbox chars={len(text_clean)}",
                                )
                                success = True
                            else:
                                store.log_event(
                                    uid,
                                    "FULLTEXT_TOO_SHORT",
                                    f"rung=4 source=inbox chars={len(text_clean)}",
                                )
                        except Exception as exc:
                            logger.error(f"[Rung 4] Failed for {uid}: {exc}")
                            store.log_event(uid, "FULLTEXT_FETCH_FAILED", f"rung=4 source=inbox error={exc}")
                    else:
                        store.log_event(uid, "FULLTEXT_FETCH_FAILED", "rung=4 source=inbox error=file_not_found")

            processed_count += 1
    finally:
        if own_client:
            client.close()

    return processed_count


# Alias for backward compatibility with FL-2 calls
fetch_arxiv_fulltext_batch = fetch_fulltext_batch


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Full-Text Acquisition Ladder Tool (D38)")
    ap.add_argument("--limit", type=int, default=10, help="Max documents to process")
    ap.add_argument("--db", type=Path, help="Override DB path (SQLite)")
    ap.add_argument("--rungs", default="1,2,3,4", help="Active ladder rungs (e.g. 1,2,3,4)")

    args = ap.parse_args(argv)

    store_path = args.db if args.db else None
    with StagingStore(store_path) if store_path else StagingStore() as store:
        count = fetch_fulltext_batch(store, limit=args.limit, rungs=args.rungs)
        print(f"Completed full-text acquisition ladder for {count} documents.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
