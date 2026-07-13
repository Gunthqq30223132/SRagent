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

from tools.warehouse.embed import get_bge_embedding, vector_to_blob

DEFAULT_DB_PATH = Path("/Users/gun/sr-agent/staging/warehouse.db")

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
    
    # Check top levels and explicit paths
    if clean_and_normalize('1. nội khoa') in path_norm or clean_and_normalize('nọi khoa') in path_norm or clean_and_normalize('nội khoa') in path_norm:
        return 'Nội khoa'
    elif clean_and_normalize('2. nhi khoa') in path_norm or clean_and_normalize('nhi khoa') in path_norm:
        return 'Nhi khoa'
    elif clean_and_normalize('16. sản - phụ khoa') in path_norm or clean_and_normalize('san - phu') in path_norm or clean_and_normalize('sản/phụ') in path_norm or clean_and_normalize('sản phụ khoa') in path_norm or clean_and_normalize('obstetric') in path_norm or clean_and_normalize('gynecology') in path_norm:
        return 'Sản phụ khoa'
    elif clean_and_normalize('7. ngoại khoa') in path_norm or clean_and_normalize('ngoai khoa') in path_norm or clean_and_normalize('ngoại khoa') in path_norm or clean_and_normalize('surgery') in path_norm or clean_and_normalize('surgical') in path_norm:
        return 'Ngoại khoa'
    elif clean_and_normalize('0. gây mê hồi sức - cấp cứu') in path_norm or clean_and_normalize('gây mê') in path_norm or clean_and_normalize('gây mê') in path_norm or clean_and_normalize('anesthesia') in path_norm or clean_and_normalize('anaesthesia') in path_norm or clean_and_normalize('anesthesiology') in path_norm or clean_and_normalize('icu') in path_norm or clean_and_normalize('critical care') in path_norm or clean_and_normalize('cấp cứu') in path_norm or clean_and_normalize('cấp cứu') in path_norm:
        return 'Gây mê hồi sức - Cấp cứu'
    elif clean_and_normalize('18 huyết học - miễn dịch') in path_norm or clean_and_normalize('huyet hoc') in path_norm or clean_and_normalize('huyết học') in path_norm or clean_and_normalize('hematology') in path_norm or clean_and_normalize('immunology') in path_norm:
        return 'Huyết học - Miễn dịch'
    elif clean_and_normalize('15. cận lâm sàng - hoá sinh') in path_norm or clean_and_normalize('hoa sinh') in path_norm or clean_and_normalize('hóa sinh') in path_norm or clean_and_normalize('biochemistry') in path_norm:
        return 'Cận lâm sàng - Hóa sinh'
    elif clean_and_normalize('5. sinh học - di truyền') in path_norm or clean_and_normalize('sinh hoc') in path_norm or clean_and_normalize('sinh học') in path_norm or clean_and_normalize('di truyền') in path_norm or clean_and_normalize('di truyền') in path_norm or clean_and_normalize('genetics') in path_norm or clean_and_normalize('biology') in path_norm:
        return 'Sinh học - Di truyền'
    elif clean_and_normalize('3. sinh lý - giải phẫu') in path_norm or clean_and_normalize('4. sách giải phẫu') in path_norm or clean_and_normalize('3. sinh lý') in path_norm or clean_and_normalize('sinh ly') in path_norm or clean_and_normalize('giải phẫu') in path_norm or clean_and_normalize('anatomy') in path_norm or clean_and_normalize('physiology') in path_norm:
        return 'Sinh lý - Giải phẫu'
    elif clean_and_normalize('6. dược lý - thủ thuật') in path_norm or clean_and_normalize('duoc ly') in path_norm or clean_and_normalize('dược lý') in path_norm or clean_and_normalize('pharmacology') in path_norm:
        # Check subfolder Gây mê in Dược lý
        if clean_and_normalize('gây mê') in path_norm or clean_and_normalize('anesthesia') in path_norm or clean_and_normalize('icu') in path_norm:
            return 'Gây mê hồi sức - Cấp cứu'
        return 'Dược lý - Thủ thuật'
    elif clean_and_normalize('13. khám') in path_norm or clean_and_normalize('kham') in path_norm or clean_and_normalize('clinical exam') in path_norm:
        return 'Khám lâm sàng'
    elif clean_and_normalize('5. luật khám chữa bệnh') in path_norm or clean_and_normalize('8. quy chế bệnh viện') in path_norm or clean_and_normalize('luật') in path_norm or clean_and_normalize('quy chế') in path_norm or clean_and_normalize('regulation') in path_norm:
        return 'Pháp luật y tế & Quy chế'

    # Token-based check for subfolders like in 0. PLAN ÔN THI or SLIDE SÂU LƯỜI HAM HỌC
    path_words = get_words(path_norm)
    file_words = get_words(file_norm)
    all_words = set(path_words + file_words)
    
    # Match specific words exactly to avoid sub-string matching like nhi in nhiễm
    if clean_and_normalize('nhi') in all_words:
        return 'Nhi khoa'
    elif clean_and_normalize('nội') in all_words or clean_and_normalize('nội') in path_norm or clean_and_normalize('nôi') in path_norm:
        return 'Nội khoa'
    elif clean_and_normalize('ngoại') in all_words or clean_and_normalize('ngoại') in path_norm or clean_and_normalize('ngoai') in path_norm:
        return 'Ngoại khoa'
    elif clean_and_normalize('sản') in all_words or clean_and_normalize('sản') in path_norm or clean_and_normalize('san') in path_norm:
        return 'Sản phụ khoa'
    elif clean_and_normalize('sinh') in all_words and (clean_and_normalize('lý') in all_words or clean_and_normalize('ly') in all_words):
        return 'Sinh lý - Giải phẫu'
    elif clean_and_normalize('giải') in all_words and (clean_and_normalize('phẫu') in all_words or clean_and_normalize('phau') in all_words):
        return 'Sinh lý - Giải phẫu'
    elif clean_and_normalize('di') in all_words and (clean_and_normalize('truyền') in all_words or clean_and_normalize('truyen') in all_words):
        return 'Sinh học - Di truyền'
    elif clean_and_normalize('hóa') in all_words and (clean_and_normalize('sinh') in all_words):
        return 'Cận lâm sàng - Hóa sinh'
    elif clean_and_normalize('dược') in all_words or clean_and_normalize('duoc') in all_words:
        return 'Dược lý - Thủ thuật'
    elif clean_and_normalize('gmhs') in all_words or clean_and_normalize('icu') in all_words or clean_and_normalize('anesthesia') in all_words or clean_and_normalize('cap') in all_words and clean_and_normalize('cuu') in all_words:
        return 'Gây mê hồi sức - Cấp cứu'
        
    # File in root or defaults
    if clean_and_normalize('truyền nhiễm') in file_norm or clean_and_normalize('truyen nhiem') in file_norm:
        return 'Nội khoa'
        
    return 'Tổng hợp / Ôn thi'

def determine_authority_tier_refined(path: str, filename: str) -> str:
    path_norm = clean_and_normalize(path)
    file_norm = clean_and_normalize(filename)
    
    # Tier 3 Rules: Internal, Slides, Exams, Regulations, etc. (High priority check)
    path_words = get_words(path_norm)
    file_words = get_words(file_norm)
    all_words = set(path_words + file_words)
    
    t3_keywords = ['slide', 'đề', 'plan', 'ôn thi', 'pretest', 'cbl', 'bài soạn', 'bảng chia', 'y lệnh', 'bệnh án', 'review', 'lượng giá', 'quy chế', 'kinh nghiệm']
    if any(clean_and_normalize(k) in path_norm for k in t3_keywords):
        return 'T3'
    t3_file_keywords = ['pretest', 'đề', 'cbl', 'lương giá', 'thi', 'chữa đề', 'slide', 'handout', 'bài giảng', 'bài báo cáo', 'phiên', 'phiếu gây mê', 'bệnh án', 'y lệnh', 'kinh nghiệm', 'câu hỏi']
    if any(clean_and_normalize(k) in file_norm for k in t3_file_keywords):
        return 'T3'
        
    # Tier 1 Rules: Guidelines and Journals
    t1_file_keywords = ['guideline', 'huong-dan', 'phac-do', 'phác đồ', 'hướng dẫn', 'quyết định', 'byt', 'bộ y tế', 'lancet', 'ssc', 'asa', 'aha', 'esc', 'acr']
    if clean_and_normalize('uptodate') in file_norm or clean_and_normalize('uptodate') in path_norm:
        return 'T1'
    if any(clean_and_normalize(k) in file_norm for k in t1_file_keywords):
        return 'T1'
    if any(clean_and_normalize(k) in path_norm for k in ['guidelines', 'hướng dẫn', 'phác đồ', 'phac-do', 'huong-dan', 'luật khám chữa bệnh']):
        return 'T1'
        
    # Tier 2 Rules: Textbooks
    t2_keywords = ['sách', 'sách', 'textbook', 'book', 'atlas', 'chestnut', 'miller', 'barash', 'guyton', 'marino', 'costanzo', 'zollinger', 'schwartz', 'hadzic', 'kaplan', 'morgan', 'hagberg', 'silbernagl', 'berne', 'stanton']
    if any(clean_and_normalize(k) in path_norm for k in t2_keywords):
        return 'T2'
    if any(clean_and_normalize(k) in file_norm for k in ['chapter', 'section', 'part', 'tập', 'textbook', 'manual', 'handbook', 'atlas', 'guidelines in practice']):
        return 'T2'
        
    # Fallback to T2 since most remaining items in medical folders are textbooks/academic books
    return 'T2'

def get_path_parts(pdf_path: str) -> Tuple[str, str]:
    """Helper to extract relative parent path and filename relative to the corpus base."""
    abs_path = os.path.abspath(pdf_path)
    corpus_base = "/Volumes/Gun SSD/1. STUDY"
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
            res = subprocess.run([mutool_path, "draw", "-o", "-", pdf_path], capture_output=True, text=True, check=True)
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
        
        # Insert chunks
        for page_idx, page_text in enumerate(pages, start=1):
            if not page_text.strip():
                continue
                
            page_chunks = chunk_page(page_text)
            for chunk_seq, (start, end, chunk_txt) in enumerate(page_chunks):
                chunk_id = f"{filename}#{page_idx:03d}#{chunk_seq:03d}"
                char_span = f"{start}-{end}"
                content_hash = hashlib.sha256(chunk_txt.encode("utf-8")).hexdigest()
                
                # Fetch embedding
                vector = get_bge_embedding(chunk_txt)
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
