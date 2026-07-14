import os
import sqlite3
import struct
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import httpx

from tools.warehouse.embed import (
    vector_to_blob,
    blob_to_vector,
    cosine_similarity,
    get_bge_embedding,
    get_bge_embeddings_batch,
)
from tools.warehouse.ingest_pdf import (
    clean_and_normalize,
    get_words,
    determine_specialty_refined,
    determine_authority_tier_refined,
    get_path_parts,
    adjust_boundary,
    chunk_page,
    extract_text_from_pdf,
    ingest_pdf,
)
from tools.warehouse.retrieve import (
    get_pinning_tokens,
    matches_pinning,
    verify_citations_or_abort,
    retrieve,
)

# ----------------- Tests for normalizations and classifiers -----------------

def test_clean_and_normalize():
    decomposed = "no\u0323\u0302i khoa"  # decomposed "nội khoa"
    composed = "nội khoa"
    assert clean_and_normalize(decomposed) == clean_and_normalize(composed)
    assert clean_and_normalize("HElLo WoRLD") == "hello world"

def test_get_words():
    text = "nội khoa, ngoại khoa & sản phụ khoa!"
    words = get_words(clean_and_normalize(text))
    assert "nội" in words
    assert "ngoại" in words
    assert "sản" in words

def test_determine_specialty_refined():
    assert determine_specialty_refined("1. nọi khoa", "doc.pdf") == "Nội khoa"
    assert determine_specialty_refined("2. nhi khoa", "doc.pdf") == "Nhi khoa"
    assert determine_specialty_refined("16. sản - phụ khoa", "doc.pdf") == "Sản phụ khoa"
    assert determine_specialty_refined("7. ngoại khoa", "doc.pdf") == "Ngoại khoa"
    assert determine_specialty_refined("0. gây mê hồi sức - cấp cứu", "doc.pdf") == "Gây mê hồi sức - Cấp cứu"
    assert determine_specialty_refined("18 huyết học - miễn dịch", "doc.pdf") == "Huyết học - Miễn dịch"
    assert determine_specialty_refined("15. cận lâm sàng - hoá sinh", "doc.pdf") == "Cận lâm sàng - Hóa sinh"
    assert determine_specialty_refined("5. sinh học - di truyền", "doc.pdf") == "Sinh học - Di truyền"
    assert determine_specialty_refined("3. sinh lý - giải phẫu", "doc.pdf") == "Sinh lý - Giải phẫu"
    assert determine_specialty_refined("6. dược lý - thủ thuật", "doc.pdf") == "Dược lý - Thủ thuật"
    assert determine_specialty_refined("6. dược lý - thủ thuật/gây mê", "doc.pdf") == "Gây mê hồi sức - Cấp cứu"
    assert determine_specialty_refined("13. khám", "doc.pdf") == "Khám lâm sàng"
    assert determine_specialty_refined("5. luật khám chữa bệnh", "doc.pdf") == "Pháp luật y tế & Quy chế"

    # Test token/subfolder fallback
    assert determine_specialty_refined("0. PLAN ÔN THI/2. NHI KHOA", "some_file.pdf") == "Nhi khoa"
    assert determine_specialty_refined("0. PLAN ÔN THI", "bài giảng nội khoa.pdf") == "Nội khoa"
    assert determine_specialty_refined("SLIDE SÂU LƯỜI HAM HỌC", "sinh lý thận.pdf") == "Sinh lý - Giải phẫu"
    assert determine_specialty_refined("", "truyền nhiễm yds.pdf") == "Nội khoa"
    assert determine_specialty_refined("random_path", "unknown.pdf") == "Tổng hợp / Ôn thi"

def test_determine_authority_tier_refined():
    assert determine_authority_tier_refined("0. PLAN ÔN THI", "de_thi_nhi.pdf") == "T3"
    assert determine_authority_tier_refined("some_folder/slide", "lecture.pdf") == "T3"
    assert determine_authority_tier_refined("some_folder", "pretest_internal.pdf") == "T3"

    assert determine_authority_tier_refined("guidelines", "sepsis_2026.pdf") == "T1"
    assert determine_authority_tier_refined("some_folder", "phac-do-dieu-tri.pdf") == "T1"
    assert determine_authority_tier_refined("some_folder", "Tinea capitis_ Clinical features and diagnosis - UpToDate.pdf") == "T1"

    assert determine_authority_tier_refined("sách", "guyton_physiology.pdf") == "T2"
    assert determine_authority_tier_refined("some_folder", "chapter_1.pdf") == "T2"
    assert determine_authority_tier_refined("some_folder", "atlas_anatomy.pdf") == "T2"
    assert determine_authority_tier_refined("some_folder", "normal_book.pdf") == "T2"

def test_get_path_parts():
    from tools.warehouse.config import CORPUS_BASE_PATH
    test_path = os.path.join(str(CORPUS_BASE_PATH), "1. NỘI KHOA/NẤM DA ĐẦU/file.pdf")
    parent, filename = get_path_parts(test_path)
    assert parent == "1. NỘI KHOA/NẤM DA ĐẦU"
    assert filename == "file.pdf"

    parent, filename = get_path_parts("/tmp/some_dir/file.pdf")
    assert parent == "/tmp/some_dir"
    assert filename == "file.pdf"


# ----------------- Tests for chunking and boundary preservation -----------------

def test_adjust_boundary():
    text = "Liều fentanyl là 2.5mcg/kg cho gây mê."
    idx = text.find("2.5") + 1
    assert text[idx] == "."
    
    adjusted = adjust_boundary(text, idx)
    assert text[adjusted].isspace() or text[adjusted - 1].isspace() or adjusted == 0 or adjusted == len(text)

def test_chunk_page():
    page_text = "Word " * 300
    chunks = chunk_page(page_text)
    assert len(chunks) > 1
    for start, end, chunk_txt in chunks:
        assert 500 <= (end - start) <= 1000 or (start == 0 and end == len(page_text))
        assert len(chunk_txt) == end - start


# ----------------- Tests for text extraction fallbacks -----------------

@patch("shutil.which")
@patch("subprocess.run")
def test_extract_text_from_pdf_pdftotext_success(mock_run, mock_which):
    mock_which.side_effect = lambda cmd: "/usr/bin/pdftotext" if cmd == "pdftotext" else None
    
    mock_res = MagicMock()
    mock_res.stdout = "page 1 text\x0cpage 2 text"
    mock_run.return_value = mock_res
    
    text = extract_text_from_pdf("mock.pdf")
    assert text == "page 1 text\x0cpage 2 text"
    mock_run.assert_called_once_with(["/usr/bin/pdftotext", "-layout", "mock.pdf", "-"], capture_output=True, text=True, check=True)

@patch("shutil.which")
@patch("subprocess.run")
def test_extract_text_from_pdf_mutool_fallback(mock_run, mock_which):
    mock_which.side_effect = lambda cmd: "/usr/bin/mutool" if cmd == "mutool" else None
    
    mock_res = MagicMock()
    mock_res.stdout = "page 1 text from mutool"
    mock_run.return_value = mock_res
    
    text = extract_text_from_pdf("mock.pdf")
    assert text == "page 1 text from mutool"
    mock_run.assert_called_once_with(["/usr/bin/mutool", "draw", "-F", "txt", "-o", "-", "mock.pdf"], capture_output=True, text=True, check=True)

@patch("shutil.which")
def test_extract_text_from_pdf_fail_closed(mock_which):
    mock_which.return_value = None
    with pytest.raises(RuntimeError, match="Missing or failing system PDF extractor"):
        extract_text_from_pdf("mock.pdf")


# ----------------- Tests for Ollama Embeddings Engine -----------------

def test_vector_conversions():
    vector = [1.0, -2.5, 3.14, 0.0]
    blob = vector_to_blob(vector)
    deserialized = blob_to_vector(blob)
    assert len(deserialized) == len(vector)
    for v_orig, v_des in zip(vector, deserialized):
        assert abs(v_orig - v_des) < 1e-5

def test_cosine_similarity():
    v1 = [1.0, 2.0, 3.0]
    v2 = [1.0, 2.0, 3.0]
    assert abs(cosine_similarity(v1, v2) - 1.0) < 1e-6
    
    v3 = [-1.0, -2.0, -3.0]
    assert abs(cosine_similarity(v1, v3) - (-1.0)) < 1e-6
    
    v_zero = [0.0, 0.0, 0.0]
    assert cosine_similarity(v1, v_zero) == 0.0
    assert cosine_similarity(v1, [1.0, 2.0]) == 0.0

@patch("httpx.post")
def test_get_bge_embeddings_batch_success(mock_post):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
    mock_post.return_value = mock_res
    
    embs = get_bge_embeddings_batch(["hello", "world"])
    assert embs == [[0.1, 0.2], [0.3, 0.4]]


# ----------------- Ingestion, Database state, and Incremental sync -----------------

@pytest.fixture
def temp_db():
    temp_fd, temp_path = tempfile.mkstemp()
    db_path = Path(temp_path)
    yield db_path
    os.close(temp_fd)
    if db_path.exists():
        db_path.unlink()

@patch("tools.warehouse.ingest_pdf.extract_text_from_pdf")
@patch("tools.warehouse.ingest_pdf.get_bge_embeddings_batch")
def test_ingestion_and_incremental(mock_get_embs, mock_extract, temp_db):
    mock_extract.return_value = "Page 1 of the document.\x0cPage 2 of the document."
    mock_get_embs.return_value = [[0.1] * 1024, [0.1] * 1024]
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"dummy pdf content")
        pdf_path = f.name
        
    try:
        ingest_pdf(pdf_path, db_path=temp_db)
        
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        
        cursor.execute("SELECT file_path, file_hash FROM indexed_files")
        files = cursor.fetchall()
        assert len(files) == 1
        assert files[0][0] == os.path.abspath(pdf_path)
        
        cursor.execute("SELECT chunk_id, page, text, authority_tier FROM chunks")
        chunks = cursor.fetchall()
        assert len(chunks) == 2
        assert chunks[0][1] == 1
        assert chunks[1][1] == 2
        assert chunks[0][3] == "T2"
        
        cursor.execute("SELECT chunk_id, text FROM chunks_fts")
        fts_rows = cursor.fetchall()
        assert len(fts_rows) == 2
        
        conn.close()
        
        mock_extract.reset_mock()
        ingest_pdf(pdf_path, db_path=temp_db)
        mock_extract.assert_not_called()
        
        with open(pdf_path, "wb") as f_mod:
            f_mod.write(b"modified pdf content")
            
        mock_extract.return_value = "Modified Page 1 text.\x0cPage 2 unchanged."
        ingest_pdf(pdf_path, db_path=temp_db)
        mock_extract.assert_called_once()
        
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("SELECT text FROM chunks ORDER BY page ASC")
        chunk_texts = [r[0] for r in cursor.fetchall()]
        assert "Modified Page 1 text." in chunk_texts[0]
        conn.close()
        
    finally:
        os.unlink(pdf_path)

@patch("tools.warehouse.ingest_pdf.extract_text_from_pdf")
@patch("tools.warehouse.ingest_pdf.get_bge_embeddings_batch")
def test_pk_collision_prevention(mock_get_embs, mock_extract, temp_db):
    """Test that two files with the same basename but in different directories 
    do not trigger database primary key collision (IntegrityError). (F8)
    """
    mock_extract.return_value = "Slide content"
    mock_get_embs.return_value = [[0.1] * 1024]
    
    with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
        file1 = os.path.join(dir1, "Slide.pdf")
        file2 = os.path.join(dir2, "Slide.pdf")
        
        with open(file1, "wb") as f1, open(file2, "wb") as f2:
            f1.write(b"pdf 1")
            f2.write(b"pdf 2")
            
        # Ingest both Slide.pdf files
        try:
            ingest_pdf(file1, db_path=temp_db)
            ingest_pdf(file2, db_path=temp_db)
        except sqlite3.IntegrityError as e:
            pytest.fail(f"Unique constraint failed / IntegrityError triggered: {e}")
            
        # Verify both exist in DB
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("SELECT chunk_id, file_path FROM chunks")
        rows = cursor.fetchall()
        assert len(rows) == 2
        # Verify chunk IDs are unique and different due to prefix hash
        assert rows[0][0] != rows[1][0]
        conn.close()


# ----------------- Retrieval, Pinning, and RRF calculations -----------------

def test_pinning_logic():
    assert "propofol" in get_pinning_tokens("Give propofol 2mg/kg")
    assert "2.5" in get_pinning_tokens("What is the dose 2.5?")
    assert "fentanyl" in get_pinning_tokens("Fentanyl infusion protocol")
    
    # Exact word matching tests
    tokens = get_pinning_tokens("propofol 1.5")
    assert matches_pinning("Propofol is an anesthetic agent.", tokens)
    assert matches_pinning("Liều dùng 1.5 mg.", tokens)
    # Substring match "nhi" should NOT match word "nhiễm"
    assert not matches_pinning("bệnh truyền nhiễm", {"nhi"})
    assert not matches_pinning("Ketamine is used for sedation.", tokens)

@patch("tools.warehouse.retrieve.get_bge_embedding")
def test_retrieval_and_rrf(mock_get_emb, temp_db):
    from tools.warehouse.ingest_pdf import init_db
    init_db(temp_db)
    
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    
    v_fentanyl = [1.0, 0.0]
    v_propofol = [0.0, 1.0]
    
    cursor.execute(
        """
        INSERT INTO chunks (chunk_id, file_path, specialty, page, char_span, text, content_hash, authority_tier, vector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("fentanyl.pdf#001#000", "fentanyl.pdf", "Gây mê", 1, "0-50", "Fentanyl is a potent opioid analgesic.", "hash1", "T1", vector_to_blob(v_fentanyl))
    )
    cursor.execute(
        "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
        ("fentanyl.pdf#001#000", "Fentanyl is a potent opioid analgesic.")
    )
    
    cursor.execute(
        """
        INSERT INTO chunks (chunk_id, file_path, specialty, page, char_span, text, content_hash, authority_tier, vector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("propofol.pdf#001#000", "propofol.pdf", "Gây mê", 1, "0-50", "Propofol is used for induction of anesthesia.", "hash2", "T1", vector_to_blob(v_propofol))
    )
    cursor.execute(
        "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
        ("propofol.pdf#001#000", "Propofol is used for induction of anesthesia.")
    )
    
    conn.commit()
    conn.close()
    
    mock_get_emb.return_value = None
    res = retrieve("fentanyl", db_path=temp_db)
    assert len(res) >= 1
    assert "Fentanyl" in res[0]["text"]
    
    mock_get_emb.return_value = [0.0, 1.0]
    res_hybrid = retrieve("induction", db_path=temp_db)
    assert len(res_hybrid) >= 1
    assert "Propofol" in res_hybrid[0]["text"]


# ----------------- Citation Check (NE4 & NE5) -----------------

def test_citation_checks_ne4_ne5(temp_db):
    from tools.warehouse.ingest_pdf import init_db
    init_db(temp_db)
    
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO chunks (chunk_id, file_path, specialty, page, char_span, text, content_hash, authority_tier)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("sepsis_guideline.pdf#012#003", "sepsis_guideline.pdf", "Cấp cứu", 12, "100-200", "Sepsis treatment guideline.", "hash3", "T1")
    )
    cursor.execute(
        """
        INSERT INTO chunks (chunk_id, file_path, specialty, page, char_span, text, content_hash, authority_tier)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("another_guideline.pdf#001#000", "another_guideline.pdf", "Nội khoa", 1, "0-50", "Another guideline text.", "hash4", "T1")
    )
    conn.commit()
    conn.close()
    
    retrieved_chunks = [
        {
            "chunk_id": "sepsis_guideline.pdf#012#003",
            "file_path": "sepsis_guideline.pdf",
            "filename": "sepsis_guideline.pdf",
            "specialty": "Cấp cứu",
            "page": 12,
            "chunk_seq": 3,
            "text": "Sepsis treatment guideline."
        }
    ]

    # Case 1: Non-directive prose without citation (passes)
    verify_citations_or_abort("The patient was admitted yesterday.", temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)
    
    # Case 2: English directive verb with valid citation (passes)
    verify_citations_or_abort("We must administer the drug immediately [sepsis_guideline.pdf#012#003].", temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)
    
    # Case 3: English directive verb without citation (aborts with SystemExit) (F5)
    with pytest.raises(SystemExit, match="Actionable directive sentence missing citation"):
        verify_citations_or_abort("We must administer the drug immediately.", temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)
        
    # Case 4: Vietnamese directive verb with valid citation (passes)
    verify_citations_or_abort("Bác sĩ cần theo dõi sát [sepsis_guideline.pdf#012#003].", temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)
    
    # Case 5: Vietnamese directive verb without citation (aborts with SystemExit) (F5)
    with pytest.raises(SystemExit, match="Actionable directive sentence missing citation"):
        verify_citations_or_abort("Bác sĩ cần theo dõi sát.", temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)
        
    # Case 6: Test Vietnamese verb "cho" does NOT trigger NE4 (word boundary / generic word protection) (P2)
    verify_citations_or_abort("Đây là thuốc cho trẻ em.", temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)

    # Case 7: Citation exists in DB and is in the retrieval set (passes)
    valid_output = "According to [sepsis_guideline.pdf#012#003], treat immediately."
    verify_citations_or_abort(valid_output, temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)
    
    # Case 8: Invalid citation token (orphan token) not present in DB (aborts with SystemExit) (F5)
    invalid_output = "According to [fake_guideline.pdf#001#000], do something."
    with pytest.raises(SystemExit, match="Orphan citation token detected"):
        verify_citations_or_abort(invalid_output, temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)
        
    # Case 9: Citation exists in DB but is NOT in the retrieval set of the current run (aborts with SystemExit) (F5)
    output_out_of_set = "According to [another_guideline.pdf#001#000], do something."
    with pytest.raises(SystemExit, match="does not belong to the retrieval set"):
        verify_citations_or_abort(output_out_of_set, temp_db, retrieved_chunks=retrieved_chunks, check_ne4=True)
