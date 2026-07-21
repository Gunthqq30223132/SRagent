"""Warehouse Document Reader (D38 Rung 3).

Reads verbatim full-text of a document from warehouse.db by matching title_normalized.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from sr_agent.models.schemas import normalize_title

logger = logging.getLogger("tools.warehouse.read_doc")


def get_document_text(title_normalized: str, db_path: Path) -> str | None:
    """Reads full-text of a document from warehouse.db by title_normalized match.

    Returns concatenated text of all chunks ordered by (page, rowid) if exactly 1 document matches.
    If 0 docs match, returns None.
    If >1 docs match, logs warning and returns None (fail-closed ambiguity check).
    """
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Check if chunks table exists
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
        ).fetchone()
        if not table_check:
            return None

        rows = conn.execute("SELECT DISTINCT file_path FROM chunks").fetchall()
        matched_files: list[str] = []
        for r in rows:
            fp = r["file_path"]
            stem = Path(fp).stem
            name = Path(fp).name
            if (
                normalize_title(stem) == title_normalized
                or normalize_title(name) == title_normalized
                or normalize_title(fp) == title_normalized
            ):
                matched_files.append(fp)

        if len(matched_files) == 0:
            return None
        if len(matched_files) > 1:
            logger.warning(
                f"Multiple warehouse documents match title_normalized {title_normalized!r}: {matched_files}"
            )
            return None

        target_fp = matched_files[0]
        chunk_rows = conn.execute(
            "SELECT text FROM chunks WHERE file_path = ? ORDER BY page ASC, rowid ASC",
            (target_fp,),
        ).fetchall()

        chunks_text = [r["text"] for r in chunk_rows if r["text"]]
        if not chunks_text:
            return None
        return "\n".join(chunks_text)
    finally:
        conn.close()
