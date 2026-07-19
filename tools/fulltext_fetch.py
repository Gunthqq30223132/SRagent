"""Full-Text Acquisition Tool (arXiv PDF -> full_text).

Downloads PDF for arXiv papers included in screening and extracts full text.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools.warehouse.ingest_pdf import extract_text_from_pdf

logger = logging.getLogger("tools.fulltext_fetch")

MIN_FULLTEXT_LENGTH = 2000


def fetch_arxiv_fulltext_batch(
    store: StagingStore,
    limit: int = 10,
    client: Optional[httpx.Client] = None,
) -> int:
    """Fetches arXiv PDFs for docs queued with SCREEN_INCLUDED and missing full_text."""
    rows = store.conn.execute(
        """
        SELECT uid FROM documents
        WHERE status = ?
          AND source = 'arxiv'
          AND uid IN (SELECT uid FROM events WHERE event_type = 'SCREEN_INCLUDED')
          AND (json_extract(payload, '$.full_text') IS NULL OR json_extract(payload, '$.full_text') = '')
        """,
        (DocStatus.QUEUED.value,),
    ).fetchall()

    to_process = [r["uid"] for r in rows]
    if not to_process:
        print("No arXiv documents require full-text acquisition.")
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

            raw_id = doc.source_id or uid
            arxiv_id = raw_id.split("arxiv:", 1)[1] if "arxiv:" in raw_id else raw_id
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            print(f"Fetching arXiv PDF: {uid} ({pdf_url})")

            tmp_path = None
            try:
                resp = client.get(pdf_url)
                if resp.status_code != 200:
                    logger.warning(f"HTTP {resp.status_code} for {pdf_url}")
                    store.log_event(uid, "FULLTEXT_FETCH_FAILED", f"HTTP {resp.status_code}")
                    processed_count += 1
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
                else:
                    store.log_event(
                        uid,
                        "FULLTEXT_TOO_SHORT",
                        f"Length: {len(text_clean)} chars (< {MIN_FULLTEXT_LENGTH})",
                    )
                processed_count += 1

            except Exception as exc:
                logger.error(f"Failed to fetch/extract full text for {uid}: {exc}")
                store.log_event(uid, "FULLTEXT_FETCH_FAILED", str(exc))
                processed_count += 1

            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
    finally:
        if own_client:
            client.close()

    return processed_count


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="arXiv Full-Text Acquisition Tool")
    ap.add_argument("--limit", type=int, default=10, help="Max documents to process")
    ap.add_argument("--db", type=Path, help="Override DB path (SQLite)")

    args = ap.parse_args(argv)

    store_path = args.db if args.db else None
    with StagingStore(store_path) if store_path else StagingStore() as store:
        count = fetch_arxiv_fulltext_batch(store, limit=args.limit)
        print(f"Completed arXiv full-text acquisition for {count} documents.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
