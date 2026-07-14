import os
import sys
import hashlib
import sqlite3
import shutil
import subprocess
import unicodedata
import re
from pathlib import Path
from typing import List, Tuple, Optional

from tools.warehouse.embed import get_bge_embeddings_batch, vector_to_blob
from tools.warehouse.config import (
    WAREHOUSE_DB_PATH,
    CORPUS_BASE_PATH,
    SPECIALTY_MAPPING,
    AUTHORITY_TIER_MAPPING
)

DEFAULT_DB_PATH = WAREHOUSE_DB_PATH

# Token pattern for boundary check: digits (with optional decimal point) or letters
token_pattern = re.compile(r'\b\d+(?:\.\d+)?\b|\w+')

def clean_and_normalize(text: str) -> str:
    """Normalize to NFC to combine diacritics and convert to lowercase."""
    text = unicodedata.normalize('NFC', text)
    return text.lower()

def get_words(text: str) -> List[str]:
    """Replace punctuation with spaces and split into words."""
    text_clean = re.sub(r'[^\w\s\u00C0-\u1EF9]', ' ', text)
    return text_clean.split()

def determine_specialty_refined(path: str, filename: str) -> str:
    path_norm = clean_and_normalize(path)
    file_norm = clean_and_normalize(filename)
    
    # Check folders map
    for keyword, specialty in SPECIALTY_MAPPING["folders"]:
        if clean_and_normalize(keyword) in path_norm:
            return specialty
            
    # Regex word-boundary check for keywords (compound and single words)
    for keyword, specialty in SPECIALTY_MAPPING["keywords"].items():
        pattern = r'\b' + re.escape(clean_and_normalize(keyword)) + r'\b'
        if re.search(pattern, path_norm) or re.search(pattern, file_norm):
            return specialty
            
    if clean_and_normalize('truyền nhiễm') in file_norm or clean_and_normalize('truyen nhiem') in file_norm:
        return 'Nội khoa'
        
    return 'Tổng hợp / Ôn thi'

def determine_authority_tier_refined(path: str, filename: str) -> str:
    path_norm = clean_and_normalize(path)
    file_norm = clean_and_normalize(filename)
    
    # Tier 3 Rules: Internal, Slides, Exams, Regulations, etc. (High priority check)
    if any(clean_and_normalize(k) in path_norm for k in AUTHORITY_TIER_MAPPING["t3_keywords"]):
        return 'T3'
    if any(clean_and_normalize(k) in file_norm for k in AUTHORITY_TIER_MAPPING["t3_file_keywords"]):
        return 'T3'
        
    # Tier 1 Rules: Guidelines and Journals
    if any(clean_and_normalize(k) in file_norm for k in AUTHORITY_TIER_MAPPING["t1_file_keywords"]):
        return 'T1'
    if any(clean_and_normalize(k) in path_norm for k in AUTHORITY_TIER_MAPPING["t1_folder_keywords"]):
        return 'T1'
        
    # Tier 2 Rules: Textbooks
    if any(clean_and_normalize(k) in path_norm for k in AUTHORITY_TIER_MAPPING["t2_folder_keywords"]):
        return 'T2'
    if any(clean_and_normalize(k) in file_norm for k in AUTHORITY_TIER_MAPPING["t2_file_keywords"]):
        return 'T2'
        
    # Fallback to T2 since most remaining items in medical folders are textbooks/academic books
    return 'T2'

def get_path_parts(pdf_path: str) -> Tuple[str, str]:
    """Helper to extract relative parent path and filename relative to the corpus base."""
    abs_path = os.path.abspath(pdf_path)
    corpus_base = str(CORPUS_BASE_PATH)
    if abs_path.startswith(corpus_base):
        rel_to_corpus = os.path.relpath(abs_path, corpus_base)
        parent_dir = os.path.dirname(rel_to_corpus)
        filename = os.path.basename(rel_to_corpus)
        return parent_dir, filename
    else:
        parent_dir = os.path.dirname(pdf_path)
        filename = os.path.basename(pdf_path)
        return parent_dir, filename

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts layout-preserved text using pdftotext or mutool fallback.
    Fail-closed and prints instruction if both fail or are missing.
    """
    pdftotext_path = shutil.which("pdftotext")
    if pdftotext_path:
        try:
            res = subprocess.run([pdftotext_path, "-layout", pdf_path, "-"], capture_output=True, text=True, check=True)
            return res.stdout
        except subprocess.CalledProcessError:
            pass
            
    mutool_path = shutil.which("mutool")
    if mutool_path:
        try:
            res = subprocess.run([mutool_path, "draw", "-F", "txt", "-o", "-", pdf_path], capture_output=True, text=True, check=True)
            return res.stdout
        except subprocess.CalledProcessError:
            pass
            
    print("Missing or failing system PDF extractor! Please run: brew install poppler")
    raise RuntimeError("Missing or failing system PDF extractor! Please run: brew install poppler")

def adjust_boundary(text: str, idx: int) -> int:
    """Adjusts idx so it doesn't split a token. If it falls inside a token,
    shifts to the nearest side that aligns with a whitespace boundary.
    """
    if idx <= 0 or idx >= len(text):
        return idx
        
    # Check if it is already next to a whitespace
    if text[idx].isspace() or text[idx-1].isspace():
        return idx
        
    # It falls in the middle of a token. Find nearest whitespace boundary.
    left_ws = idx
    while left_ws > 0 and not text[left_ws-1].isspace():
        left_ws -= 1
    right_ws = idx
    while right_ws < len(text) and not text[right_ws].isspace():
        right_ws += 1
        
    if (idx - left_ws) <= (right_ws - idx):
        return left_ws
    else:
        return right_ws

def chunk_page(page_text: str) -> List[Tuple[int, int, str]]:
    """Chunks page text into pieces of 500-1000 characters with 10% overlap."""
    chunks = []
    L = len(page_text)
    if L == 0:
        return []
        
    if L <= 1000:
        return [(0, L, page_text)]
        
    start = 0
    while start < L:
        if L - start <= 1000:
            chunks.append((start, L, page_text[start:L]))
            break
            
        target_end = start + 900
        end = adjust_boundary(page_text, target_end)
        
        if end <= start:
            end = start + 900
            
        if end - start < 500 and L - start >= 500:
            target_end = start + 500
            end = adjust_boundary(page_text, target_end)
            if end <= start:
                end = start + 500
                
        if end - start > 1000:
            end = adjust_boundary(page_text, start + 1000)
            if end <= start:
                end = start + 1000
                
        chunks.append((start, end, page_text[start:end]))
        
        chunk_len = end - start
        overlap = int(chunk_len * 0.1)
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start
        
    return chunks

def init_db(db_path: Path):
    """Initializes the database schema if tables do not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

def ingest_pdf(pdf_path: str, db_path: Path = DEFAULT_DB_PATH):
    """Ingests a PDF file, chunking it, getting embeddings, and updating the database."""
    init_db(db_path)
    
    # Calculate SHA-256 hash of the physical file
    sha256 = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    file_hash = sha256.hexdigest()
    
    # Format database path references as path string
    pdf_path_str = os.path.abspath(pdf_path)
    
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    cursor = conn.cursor()
    
    try:
        # Check if the file is already indexed and unchanged
        cursor.execute("SELECT file_hash FROM indexed_files WHERE file_path = ?", (pdf_path_str,))
        row = cursor.fetchone()
        if row and row[0] == file_hash:
            # File is unchanged, skip indexing
            return
            
        # Extract relative path and filename to classify
        parent_dir, filename = get_path_parts(pdf_path_str)
        specialty = determine_specialty_refined(parent_dir, filename)
        authority_tier = determine_authority_tier_refined(parent_dir, filename)
        
        # Extract text from the PDF
        text = extract_text_from_pdf(pdf_path_str)
        
        # Segment text page-by-page using \x0c
        pages = text.split("\x0c")
        if pages and not pages[-1].strip():
            pages = pages[:-1]
            
        # Delete old entries from chunks, chunks_fts, and indexed_files
        cursor.execute("SELECT chunk_id FROM chunks WHERE file_path = ?", (pdf_path_str,))
        old_chunk_ids = [r[0] for r in cursor.fetchall()]
        for cid in old_chunk_ids:
            cursor.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (cid,))
        cursor.execute("DELETE FROM chunks WHERE file_path = ?", (pdf_path_str,))
        cursor.execute("DELETE FROM indexed_files WHERE file_path = ?", (pdf_path_str,))
        
        # Collect all chunk texts to compute embeddings in batch
        all_chunks_to_insert = []
        for page_idx, page_text in enumerate(pages, start=1):
            if not page_text.strip():
                continue
                
            page_chunks = chunk_page(page_text)
            for chunk_seq, (start, end, chunk_txt) in enumerate(page_chunks):
                all_chunks_to_insert.append({
                    "page_idx": page_idx,
                    "start": start,
                    "end": end,
                    "chunk_seq": chunk_seq,
                    "text": chunk_txt
                })
                
        # Batch fetch embeddings
        chunk_texts = [c["text"] for c in all_chunks_to_insert]
        embeddings = get_bge_embeddings_batch(chunk_texts)
        
        # Insert chunks
        # Use relative path hash + filename as chunk_id prefix to prevent Unique Constraint collisions (F8)
        rel_path = os.path.join(parent_dir, filename)
        path_hash = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:8]
        
        for c, vector in zip(all_chunks_to_insert, embeddings):
            page_idx = c["page_idx"]
            start = c["start"]
            end = c["end"]
            chunk_seq = c["chunk_seq"]
            chunk_txt = c["text"]
            
            chunk_id = f"{path_hash}_{filename}#{page_idx:03d}#{chunk_seq:03d}"
            char_span = f"{start}-{end}"
            content_hash = hashlib.sha256(chunk_txt.encode("utf-8")).hexdigest()
            vector_blob = vector_to_blob(vector) if vector is not None else None
            
            cursor.execute(
                """
                INSERT INTO chunks (
                    chunk_id, file_path, specialty, page, char_span, text, content_hash, authority_tier, vector
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, pdf_path_str, specialty, page_idx, char_span, chunk_txt, content_hash, authority_tier, vector_blob)
            )
            
            cursor.execute(
                "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
                (chunk_id, chunk_txt)
            )
            
        # Update indexed_files hash
        cursor.execute(
            "INSERT OR REPLACE INTO indexed_files (file_path, file_hash) VALUES (?, ?)",
            (pdf_path_str, file_hash)
        )
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m tools.warehouse.ingest_pdf <pdf_path>")
        sys.exit(1)
    pdf_path_arg = sys.argv[1]
    ingest_pdf(pdf_path_arg)
