import os
import sqlite3
import pytest
import respx
import httpx

from tools.compliance.kb import (
    ingest_markdown_table,
    search,
    Node,
    init_db,
    blob_to_vector,
    vector_to_blob,
    cosine_similarity
)

@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test_kb.db")

@pytest.fixture
def mock_markdown(tmp_path):
    content = """
| Package A | Operator A | Version A | Package B | Operator B | Version B | Condition | Action |
|---|---|---|---|---|---|---|---|
| nginx | >= | 1.19.0 | apache2 | * | * | default | rollback |
| postgres | == | 14.2.10 | mysql | < | 8.0.0 | dev | restart |
| redis | >= | 6.2.10 | memcached | * | * | prod | scale |
"""
    file_path = tmp_path / "table.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(file_path)

@pytest.fixture
def doc_meta_prod():
    return {
        "doc_id": "rfc_test",
        "version": "2026-07",
        "domain": "packaging",
        "authority_tier": "T2",
        "layer": "L2_local_runbook",
        "namespace": "prod",
        "effective_date": "2026-07-08",
    }

def test_ingest_markdown_table_success(temp_db, mock_markdown, doc_meta_prod):
    # Ingest mock markdown table
    nodes = ingest_markdown_table(mock_markdown, doc_meta_prod, db_path=temp_db)
    
    assert len(nodes) == 3
    for seq, node in enumerate(nodes):
        assert isinstance(node, Node)
        assert node.doc_id == "rfc_test"
        assert node.chunk_seq == seq
        assert node.status == "active"
        assert f"rfc_test#00{seq}-" in node.node_id
        
        # Verify header is repeated in node content
        assert "Package A:" in node.content
        assert "Version A:" in node.content
        assert "Package B:" in node.content
        assert "XUNG KHẮC" in node.content

    # Connect to DB and verify records are saved
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM nodes WHERE status='active'")
    assert cursor.fetchone()[0] == 3
    
    # Verify known entities got inserted
    cursor.execute("SELECT entity FROM known_entities")
    entities = {row[0] for row in cursor.fetchall()}
    assert "nginx" in entities
    assert "14.2.10" in entities
    assert "6.2.10" in entities
    assert "memcached" in entities
    conn.close()

def test_byte_exact_preservation(temp_db, mock_markdown, doc_meta_prod):
    ingest_markdown_table(mock_markdown, doc_meta_prod, db_path=temp_db)
    
    # Verify byte-exact values in nodes
    results = search("14.2.10", namespace="prod", db_path=temp_db)
    assert len(results) >= 1
    assert "14.2.10" in results[0].content
    import re
    assert not re.search(r'\b14\.2\.1\b', results[0].content)

def test_known_entity_pinning(temp_db, mock_markdown, doc_meta_prod):
    ingest_markdown_table(mock_markdown, doc_meta_prod, db_path=temp_db)
    
    # Search containing "redis", which is in known_entities
    results = search("redis scale-up info", namespace="prod", db_path=temp_db)
    assert len(results) > 0
    # The first node returned must contain "redis" because it is a matched known entity
    assert "redis" in results[0].content.lower()

def test_namespace_isolation(temp_db, mock_markdown, doc_meta_prod, tmp_path):
    # Ingest production nodes
    ingest_markdown_table(mock_markdown, doc_meta_prod, db_path=temp_db)
    
    # Ingest staging / run specific nodes
    staging_meta = doc_meta_prod.copy()
    staging_meta["namespace"] = "sr_run_999"
    staging_meta["doc_id"] = "rfc_staging"
    
    staging_content = """
| Package A | Operator A | Version A | Package B | Operator B | Version B | Condition | Action |
|---|---|---|---|---|---|---|---|
| httpd | >= | 2.4 | tomcat | * | * | staging | restart |
"""
    staging_file = tmp_path / "staging.md"
    with open(staging_file, "w", encoding="utf-8") as f:
        f.write(staging_content)
        
    ingest_markdown_table(str(staging_file), staging_meta, db_path=temp_db)
    
    # Search in prod namespace
    prod_results = search("httpd tomcat", namespace="prod", db_path=temp_db)
    # Staging node should not appear in production namespace search
    for node in prod_results:
        assert "httpd" not in node.content
        
    # Search in staging namespace
    staging_results = search("httpd", namespace="sr_run_999", db_path=temp_db)
    assert len(staging_results) == 1
    assert "httpd" in staging_results[0].content

def test_supersede_chain(temp_db, mock_markdown, doc_meta_prod, tmp_path):
    # First ingestion
    ingest_markdown_table(mock_markdown, doc_meta_prod, db_path=temp_db)
    
    # Second table with modified second row (postgres version changed)
    modified_content = """
| Package A | Operator A | Version A | Package B | Operator B | Version B | Condition | Action |
|---|---|---|---|---|---|---|---|
| nginx | >= | 1.19.0 | apache2 | * | * | default | rollback |
| postgres | == | 15.0.0 | mysql | < | 8.0.0 | dev | restart |
| redis | >= | 6.2.10 | memcached | * | * | prod | scale |
"""
    modified_file = tmp_path / "modified.md"
    with open(modified_file, "w", encoding="utf-8") as f:
        f.write(modified_content)
        
    # Ingest same doc_id and seq but with updated content
    ingest_markdown_table(str(modified_file), doc_meta_prod, db_path=temp_db)
    
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    # Verify supersede chain
    cursor.execute("SELECT node_id, status, superseded_by FROM nodes WHERE chunk_seq=1")
    rows = cursor.fetchall()
    
    # There should be 2 nodes for chunk_seq=1 now: one active (version 15.0.0) and one superseded (version 14.2.10)
    assert len(rows) == 2
    statuses = {r[1] for r in rows}
    assert "active" in statuses
    assert "superseded" in statuses
    
    superseded_node = [r for r in rows if r[1] == "superseded"][0]
    active_node = [r for r in rows if r[1] == "active"][0]
    
    # Old node points to new node
    assert superseded_node[2] == active_node[0]
    conn.close()
    
    # Default search should not return superseded nodes
    results = search("postgres", namespace="prod", db_path=temp_db)
    assert len(results) == 1
    assert "15.0.0" in results[0].content
    assert "14.2.10" not in results[0].content
    
    # Search specifically for superseded nodes
    results_superseded = search("postgres", namespace="prod", db_path=temp_db, status="superseded")
    assert len(results_superseded) == 1
    assert "14.2.10" in results_superseded[0].content

@respx.mock
def test_ollama_fallback_resiliency(temp_db, mock_markdown, doc_meta_prod):
    # Scenario 1: SR_EMBED_MODEL is empty (TẮT)
    os.environ["SR_EMBED_MODEL"] = ""
    nodes = ingest_markdown_table(mock_markdown, doc_meta_prod, db_path=temp_db)
    assert len(nodes) == 3
    
    # Run search, should execute purely via FTS5 without error
    results = search("nginx", namespace="prod", db_path=temp_db)
    assert len(results) >= 1
    assert "nginx" in results[0].content
    
    # Scenario 2: SR_EMBED_MODEL is set but Ollama fails
    os.environ["SR_EMBED_MODEL"] = "bge-m3"
    # Mock Ollama server connection failure
    respx.post("http://localhost:11434/api/embeddings").mock(side_effect=httpx.ConnectError("Connection refused"))
    
    # Ingestion and search should fallback silently to FTS5 without error
    nodes2 = ingest_markdown_table(mock_markdown, doc_meta_prod, db_path=temp_db)
    assert len(nodes2) == 3
    
    results2 = search("nginx", namespace="prod", db_path=temp_db)
    assert len(results2) >= 1
    assert "nginx" in results2[0].content
    
    # Scenario 3: Ollama succeeds
    dummy_vector = [0.1] * 384
    respx.post("http://localhost:11434/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": dummy_vector})
    )
    
    # This ingestion should save vector data
    nodes3 = ingest_markdown_table(mock_markdown, doc_meta_prod, db_path=temp_db)
    assert len(nodes3) == 3
    
    # Connect and check that vector is not null
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT vector FROM nodes WHERE node_id = ?", (nodes3[0].node_id,))
    vec_blob = cursor.fetchone()[0]
    assert vec_blob is not None
    assert len(blob_to_vector(vec_blob)) == 384
    conn.close()
    
    # Search should run with RRF/vector search successfully
    results3 = search("nginx", namespace="prod", db_path=temp_db)
    assert len(results3) >= 1
