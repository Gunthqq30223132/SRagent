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


def generate_prisma_report(store: StagingStore) -> str:
    conn = store.conn
    
    # 1. Identification
    # Sum fetched from runs
    total_fetched_runs = 0
    total_duplicates_runs = 0
    total_rubric_rejected_runs = 0
    
    for row in conn.execute("SELECT report_json FROM runs"):
        try:
            report = json.loads(row["report_json"])
            total_fetched_runs += report.get("fetched", 0)
            total_duplicates_runs += report.get("duplicates", 0)
            total_rubric_rejected_runs += report.get("rejected_by_rubric", 0)
        except Exception:
            pass
            
    # Fallback to events
    fetched_events = conn.execute("SELECT COUNT(*) n FROM events WHERE event_type = 'FETCHED'").fetchone()["n"]
    identified = max(total_fetched_runs, fetched_events)
    
    # Duplicates
    dup_events = conn.execute(
        "SELECT COUNT(*) n FROM events WHERE event_type IN ('DUPLICATE_ID', 'DUPLICATE_FUZZY')"
    ).fetchone()["n"]
    duplicates_removed = max(total_duplicates_runs, dup_events)
    
    # Rubric rejected
    rubric_events = conn.execute(
        "SELECT COUNT(*) n FROM events WHERE event_type = 'REJECTED' AND detail LIKE '%rubric%'"
    ).fetchone()["n"]
    # Also fallback to status REJECTED if no events
    rubric_docs = conn.execute(
        "SELECT COUNT(*) n FROM documents WHERE status = 'rejected' AND uid NOT IN (SELECT DISTINCT uid FROM screening)"
    ).fetchone()["n"]
    rubric_rejected = max(total_rubric_rejected_runs, rubric_events, rubric_docs)
    
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
        f"    ID[Identified: {identified} records] --> DUP[Duplicates Removed: {duplicates_removed} records]",
        f"    DUP --> RUB[Quality Gate Excluded: {rubric_rejected} records]",
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
