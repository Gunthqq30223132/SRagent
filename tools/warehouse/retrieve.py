import os
import sys
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple

from tools.warehouse.embed import get_bge_embedding, blob_to_vector, cosine_similarity
from tools.warehouse.config import WAREHOUSE_DB_PATH

DEFAULT_DB_PATH = WAREHOUSE_DB_PATH

def get_pinning_tokens(query: str) -> Set[str]:
    """Identify query tokens that represent numbers or drug names."""
    tokens = re.findall(r'\b\d+(?:\.\d+)?\b|\b\w+\b', query.lower())
    pinning_tokens = set()
    
    # List of common drug names to check
    known_drugs = {
        "fentanyl", "morphine", "propofol", "ketamine", "lidocaine", "adrenaline", 
        "epinephrine", "paracetamol", "midazolam", "atropine", "rocuronium", 
        "suxamethonium", "neostigmine", "sufentanil", "dexmedetomidine", "diazepam", 
        "heparin", "insulin", "salbutamol", "ipratropium", "budesonide", 
        "hydrocortisone", "methylprednisolone", "dexamethasone", "ceftriaxone", 
        "amoxicillin", "vancomycin", "meropenem", "imipenem", "metronidazole", 
        "gentamicin", "furosemide", "spironolactone", "captopril", "enalapril", 
        "losartan", "amlodipine", "nifedipine", "diltiazem", "verapamil", "digoxin", 
        "amiodarone", "dobutamine", "dopamine", "noradrenaline", "norepinephrine", 
        "vasopressin", "phenylephrine", "oxytocin", "carboprost", "misoprostol", 
        "ergometrine", "tranexamic", "ibuprofen", "diclofenac", "ketorolac", 
        "naloxone", "flumazenil", "vecuronium", "pancuronium", "cisatracurium"
    }
    
    for t in tokens:
        # Number check (must contain digits)
        if any(c.isdigit() for c in t):
            pinning_tokens.add(t)
        # Drug name check
        elif t in known_drugs:
            pinning_tokens.add(t)
            
    return pinning_tokens

def matches_pinning(text: str, pinning_tokens: Set[str]) -> bool:
    """Check if any pinning token is matched using exact word boundary in the text."""
    text_lower = text.lower()
    for token in pinning_tokens:
        pattern = r'\b' + re.escape(token) + r'\b'
        if re.search(pattern, text_lower):
            return True
    return False

# ----------------- Citation and Directive Rules Validation (NE4 & NE5) -----------------

DIRECTIVE_VERBS = [
    # English
    "must", "should", "shall", "require", "recommend", "administer", "give", "avoid", 
    "perform", "monitor", "assess", "use", "treat", "prescribe", "check", "consider", 
    "inject", "intubate", "infuse", "prepare", "contraindicated", "indicated",
    # Vietnamese
    "cần", "nên", "phải", "yêu cầu", "khuyến cáo", "tránh", "chỉ định", "chống chỉ định", 
    "dùng", "sử dụng", "tiêm", "truyền", "đánh giá", "theo dõi", "kiểm tra", 
    "đặt nội khí quản", "chuẩn bị", "hướng dẫn"
]

# Sort verbs by length descending to match multi-word phrases correctly, and compile into a case-insensitive regex pattern
sorted_verbs = sorted(DIRECTIVE_VERBS, key=len, reverse=True)
pattern_parts = [r'\b' + re.escape(verb) + r'\b' for verb in sorted_verbs]
DIRECTIVE_REGEX = re.compile('|'.join(pattern_parts), re.IGNORECASE)

def split_sentences(text: str) -> List[str]:
    """Splits text into sentences based on punctuation, ignoring decimal points in numbers."""
    parts = re.split(r"\.(?=\s|$)|[!?]|\n", text)
    return [p.strip() for p in parts if p.strip()]

def verify_citations_or_abort(output_text: str, db_path: Path, retrieved_chunks: List[Dict[str, Any]] = None, check_ne4: bool = True):
    """Scans all output text for citation tokens [file_name#page#chunk_seq],
    verifies their existence in warehouse.db, enforces that they belong to the
    retrieved set of the current run (NE5), and checks that sentences containing
    directive verbs have inline citations (NE4).
    Aborts immediately if any mismatch is found.
    """
    # 1. NE4 Check: sentences with directive verbs must contain an inline citation token
    if check_ne4:
        sentences = split_sentences(output_text)
        for sentence in sentences:
            if DIRECTIVE_REGEX.search(sentence):
                citation_match = re.search(r"\[[a-zA-Z0-9_\.-]+#\d+#\d+\]", sentence)
                if not citation_match:
                    raise SystemExit(
                        f"CRITICAL: Actionable directive sentence missing citation: '{sentence}'. Aborting execution."
                    )

    # 2. NE5 Check: verify citation tokens exist in DB and belong to retrieval set
    tokens = re.findall(r"\[([a-zA-Z0-9_\.-]+)#(\d+)#(\d+)\]", output_text)
    if not tokens:
        return

    # NE5 - part 1: check existence in warehouse.db first (EXACT match only - no LIKE)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        for filename, page_str, seq_str in tokens:
            page = int(page_str)
            seq = int(seq_str)
            chunk_id = f"{filename}#{page:03d}#{seq:03d}"

            cursor.execute("SELECT 1 FROM chunks WHERE chunk_id = ?", (chunk_id,))
            if not cursor.fetchone():
                raise SystemExit(
                    f"CRITICAL: Orphan citation token detected [{filename}#{page_str}#{seq_str}]. Aborting execution."
                )
    finally:
        conn.close()

    # NE5 - part 2: check against the retrieval set of the current run (EXACT match only)
    if retrieved_chunks is not None:
        retrieved_ids = set()
        for chunk in retrieved_chunks:
            cid = chunk.get("chunk_id")
            if cid:
                retrieved_ids.add(cid)

        for filename, page_str, seq_str in tokens:
            page = int(page_str)
            seq = int(seq_str)
            chunk_id = f"{filename}#{page:03d}#{seq:03d}"
            
            if chunk_id not in retrieved_ids:
                raise SystemExit(
                    f"CRITICAL: Citation [{filename}#{page_str}#{seq_str}] does not belong to the retrieval set of the current run. Aborting execution."
                )

def retrieve(query: str, db_path: Path = DEFAULT_DB_PATH, top_n: int = 5) -> List[Dict[str, Any]]:
    """Hybrid search executing FTS5 and optional Ollama embeddings, merged via RRF and pinned."""
    if not db_path.exists():
        return []
        
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    cursor = conn.cursor()
    
    try:
        # Extract query tokens for FTS5
        query_tokens = [t.strip() for t in re.findall(r'[a-zA-Z0-9_.-]+', query) if t.strip()]
        
        fts_results = []
        if query_tokens:
            def run_fts(match_q: str) -> List[Dict[str, Any]]:
                cursor.execute(
                    """
                    SELECT c.chunk_id, c.file_path, c.specialty, c.page, c.char_span, c.text, c.content_hash, c.authority_tier, c.vector
                    FROM chunks c
                    JOIN chunks_fts f ON c.chunk_id = f.chunk_id
                    WHERE f.chunks_fts MATCH ?
                    ORDER BY bm25(chunks_fts) ASC
                    LIMIT 200
                    """,
                    (match_q,)
                )
                nodes = []
                for row in cursor.fetchall():
                    cid_parts = row[0].split('#')
                    filename = cid_parts[0] if len(cid_parts) > 0 else os.path.basename(row[1])
                    try:
                        chunk_seq = int(cid_parts[2])
                    except (IndexError, ValueError):
                        chunk_seq = 0
                    nodes.append({
                        "chunk_id": row[0],
                        "file_path": row[1],
                        "filename": filename,
                        "specialty": row[2],
                        "page": row[3],
                        "char_span": row[4],
                        "text": row[5],
                        "content_hash": row[6],
                        "authority_tier": row[7],
                        "vector": row[8],
                        "chunk_seq": chunk_seq
                    })
                return nodes

            # Attempt AND query first
            and_q = " AND ".join(f'"{w}"' for w in query_tokens)
            fts_results = run_fts(and_q)
            if not fts_results:
                # Fallback to OR query
                or_q = " OR ".join(f'"{w}"' for w in query_tokens)
                fts_results = run_fts(or_q)
                
        # Vector embeddings search
        query_vector = get_bge_embedding(query)
        vector_results = []
        if query_vector:
            # Perf Opt: Only perform cosine similarity on FTS5 top-k subset if present
            if fts_results:
                fts_cids = [r["chunk_id"] for r in fts_results]
                placeholders = ",".join("?" for _ in fts_cids)
                cursor.execute(
                    f"""
                    SELECT chunk_id, file_path, specialty, page, char_span, text, content_hash, authority_tier, vector
                    FROM chunks
                    WHERE chunk_id IN ({placeholders})
                    """,
                    fts_cids
                )
            else:
                # Fallback: scan up to 500 chunks only to prevent memory/perf issues
                cursor.execute(
                    """
                    SELECT chunk_id, file_path, specialty, page, char_span, text, content_hash, authority_tier, vector
                    FROM chunks
                    LIMIT 500
                    """
                )
                
            for row in cursor.fetchall():
                vector_blob = row[8]
                if vector_blob:
                    vec = blob_to_vector(vector_blob)
                    sim = cosine_similarity(query_vector, vec)
                    cid_parts = row[0].split('#')
                    filename = cid_parts[0] if len(cid_parts) > 0 else os.path.basename(row[1])
                    try:
                        chunk_seq = int(cid_parts[2])
                    except (IndexError, ValueError):
                        chunk_seq = 0
                    node = {
                        "chunk_id": row[0],
                        "file_path": row[1],
                        "filename": filename,
                        "specialty": row[2],
                        "page": row[3],
                        "char_span": row[4],
                        "text": row[5],
                        "content_hash": row[6],
                        "authority_tier": row[7],
                        "vector": row[8],
                        "chunk_seq": chunk_seq
                    }
                    vector_results.append((node, sim))
                    
            # Sort by similarity descending
            vector_results.sort(key=lambda x: x[1], reverse=True)
            
        # Merge via Reciprocal Rank Fusion (RRF)
        if query_vector and vector_results:
            rrf_scores = {}
            chunk_map = {}
            
            for rank, chunk in enumerate(fts_results, start=1):
                cid = chunk["chunk_id"]
                chunk_map[cid] = chunk
                rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60.0 + rank))
                
            for rank, (chunk, sim) in enumerate(vector_results, start=1):
                cid = chunk["chunk_id"]
                chunk_map[cid] = chunk
                rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60.0 + rank))
                
            sorted_cids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
            final_results = [chunk_map[cid] for cid in sorted_cids]
        else:
            final_results = fts_results
            
        # Pinning exact matches of drug names or numbers (limited to top 2 to avoid RRF dilution)
        pinning_tokens = get_pinning_tokens(query)
        if pinning_tokens:
            pinned = []
            others = []
            for chunk in final_results:
                if matches_pinning(chunk["text"], pinning_tokens):
                    pinned.append(chunk)
                else:
                    others.append(chunk)
            final_results = pinned[:2] + others + pinned[2:]
            
        return final_results[:top_n]
    finally:
        conn.close()

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tools.warehouse.retrieve \"<query>\"")
        sys.exit(1)
        
    query = sys.argv[1]
    results = retrieve(query)
    
    if not results:
        print("No results found.")
        return
        
    # Generate the output text format - keep raw exact chunk text
    output_lines = []
    for i, res in enumerate(results, start=1):
        output_lines.append(f"Result {i} [{res['specialty']} / {res['authority_tier']}]:")
        citation = f"[{res['filename']}#{res['page']:03d}#{res['chunk_seq']:03d}]"
        output_lines.append(citation)
        output_lines.append(res['text'])
        output_lines.append("-" * 60)
        
    output_text = "\n".join(output_lines)
    print(output_text)
    
    # Run the verbatim citation check before exiting (check_ne4=False since search output is raw text citation)
    verify_citations_or_abort(output_text, DEFAULT_DB_PATH, retrieved_chunks=results, check_ne4=False)

if __name__ == "__main__":
    main()
