import os
import re
import hashlib
import sqlite3
import struct
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Tuple
from pydantic import BaseModel, Field
import httpx

from sr_agent.config import DB_PATH

logger = logging.getLogger(__name__)

# --- Pydantic Schema ---

class Node(BaseModel):
    node_id: str
    doc_id: str
    version: Optional[str] = None
    status: Literal["draft", "active", "superseded"]
    domain: Literal["networking", "packaging", "storage", "security", "scheduling"]
    authority_tier: Literal["T1", "T2", "T3"]
    layer: Literal["L1_canonical", "L2_local_runbook"]
    namespace: str
    conflict_flag: Optional[str] = None
    effective_date: Optional[str] = None
    sha256_12: str
    content: str
    superseded_by: Optional[str] = None
    chunk_seq: int

# --- Vector Conversion Utilities ---

def vector_to_blob(vector: List[float]) -> bytes:
    """Serializes a list of floats to float32 binary BLOB."""
    return struct.pack(f"{len(vector)}f", *vector)

def blob_to_vector(blob: bytes) -> List[float]:
    """Deserializes a float32 binary BLOB to a list of floats."""
    if not blob:
        return []
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(x * y for x, y in zip(v1, v2))
    norm_v1 = math.sqrt(sum(x * x for x in v1))
    norm_v2 = math.sqrt(sum(y * y for y in v2))
    if norm_v1 == 0.0 or norm_v2 == 0.0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

# --- DB Initialization ---

def init_db(conn: sqlite3.Connection):
    """Initializes tables and virtual tables in the database."""
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS nodes (
        node_id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        version TEXT,
        status TEXT NOT NULL,
        domain TEXT NOT NULL,
        authority_tier TEXT NOT NULL,
        layer TEXT NOT NULL,
        namespace TEXT NOT NULL,
        conflict_flag TEXT,
        effective_date TEXT,
        sha256_12 TEXT NOT NULL,
        content TEXT NOT NULL,
        superseded_by TEXT,
        chunk_seq INTEGER NOT NULL,
        vector BLOB
    )
    """)
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
        node_id UNINDEXED,
        content
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS known_entities (
        entity TEXT PRIMARY KEY
    )
    """)
    conn.commit()

# --- Embedding Helper ---

def get_embedding(text: str) -> Optional[List[float]]:
    """Calls Ollama embeddings API if a model is set in SR_EMBED_MODEL."""
    model = os.getenv("SR_EMBED_MODEL", "").strip()
    if not model:
        # FTS5-only mode line log
        logger.info("Ollama embedding model not configured (SR_EMBED_MODEL is empty). Running in FTS5-only mode.")
        return None
    
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    url = f"{ollama_base}/api/embeddings"
    try:
        response = httpx.post(
            url,
            json={"model": model, "prompt": text},
            timeout=5.0
        )
        if response.status_code == 200:
            return response.json().get("embedding")
        else:
            logger.warning(f"Ollama returned status code {response.status_code}. Falling back to FTS5-only.")
    except Exception as e:
        logger.warning(f"Failed to fetch embedding from Ollama: {e}. Falling back to FTS5-only.")
    return None

# --- Ingestion helpers ---

def parse_markdown_tables(md_content: str) -> List[Tuple[List[str], List[List[str]]]]:
    """Parses markdown content to extract tables.
    Returns a list of tuples containing (headers, rows).
    """
    tables = []
    lines = [line.strip() for line in md_content.splitlines()]
    
    current_headers = None
    current_rows = []
    in_table = False
    
    for line in lines:
        if not line:
            if in_table:
                if current_headers and current_rows:
                    tables.append((current_headers, current_rows))
                current_headers = None
                current_rows = []
                in_table = False
            continue
            
        if line.startswith("|") or "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if line.startswith("|"):
                parts = parts[1:]
            if line.endswith("|"):
                parts = parts[:-1]
                
            is_separator = all(re.match(r'^:?-+:?$', p) for p in parts) if parts else False
            
            if is_separator:
                in_table = True
                continue
                
            if not current_headers:
                current_headers = parts
                in_table = True
            else:
                current_rows.append(parts)
        else:
            if in_table:
                if current_headers and current_rows:
                    tables.append((current_headers, current_rows))
                current_headers = None
                current_rows = []
                in_table = False
                
    if in_table and current_headers and current_rows:
        tables.append((current_headers, current_rows))
        
    return tables

def format_node_content(headers: List[str], row: List[str]) -> str:
    """Formats a single row into node content, keeping version numbers byte-exact."""
    kv_pairs = []
    for h, r in zip(headers, row):
        kv_pairs.append(f"{h}: {r}")
    base_content = " | ".join(kv_pairs)
    
    normalized_headers = [h.lower().replace(" ", "").replace("_", "").replace("-", "") for h in headers]
    
    # 1. Package Conflict Matrix Check
    pkg_a_idx = -1
    op_a_idx = -1
    ver_a_idx = -1
    pkg_b_idx = -1
    op_b_idx = -1
    ver_b_idx = -1
    cond_idx = -1
    action_idx = -1
    
    for i, nh in enumerate(normalized_headers):
        if nh in {"pkga", "packagea", "pkg1", "package1"}:
            pkg_a_idx = i
        elif nh in {"opa", "operatora", "op1", "operator1"}:
            op_a_idx = i
        elif nh in {"vera", "versiona", "ver1", "version1"}:
            ver_a_idx = i
        elif nh in {"pkgb", "packageb", "pkg2", "package2"}:
            pkg_b_idx = i
        elif nh in {"opb", "operatorb", "op2", "operator2"}:
            op_b_idx = i
        elif nh in {"verb", "versionb", "ver2", "version2"}:
            ver_b_idx = i
        elif nh in {"cond", "condition", "dieukien", "dieukienkhac"}:
            cond_idx = i
        elif nh in {"action", "hanhdong", "actionwhenexceeded"}:
            action_idx = i
            
    if pkg_a_idx != -1 and pkg_b_idx != -1:
        pkg_a = row[pkg_a_idx]
        op_a = row[op_a_idx] if op_a_idx != -1 else ""
        ver_a = row[ver_a_idx] if ver_a_idx != -1 else ""
        pkg_b = row[pkg_b_idx]
        op_b = row[op_b_idx] if op_b_idx != -1 else ""
        ver_b = row[ver_b_idx] if ver_b_idx != -1 else ""
        cond = row[cond_idx] if cond_idx != -1 else "default"
        action = row[action_idx] if action_idx != -1 else "rollback"
        
        conflict_str = f"{pkg_a} {op_a}{ver_a} XUNG KHẮC {pkg_b} {op_b}{ver_b} — điều kiện: {cond} — hành động: {action}"
        return f"{base_content}\n{conflict_str}"
        
    # 2. Hardware Threshold Check
    comp_idx = -1
    metric_idx = -1
    thresh_idx = -1
    unit_idx = -1
    act_exc_idx = -1
    
    for i, nh in enumerate(normalized_headers):
        if nh in {"component", "thietbi", "phancung"}:
            comp_idx = i
        elif nh in {"metric", "chiso"}:
            metric_idx = i
        elif nh in {"threshold", "nguong"}:
            thresh_idx = i
        elif nh in {"unit", "donvi"}:
            unit_idx = i
        elif nh in {"actionwhenexceeded", "hanhdongkhiyuot", "action", "hanhdong"}:
            act_exc_idx = i
            
    if comp_idx != -1 and metric_idx != -1 and thresh_idx != -1:
        comp = row[comp_idx]
        metric = row[metric_idx]
        thresh = row[thresh_idx]
        unit = row[unit_idx] if unit_idx != -1 else ""
        act_exc = row[act_exc_idx] if act_exc_idx != -1 else ""
        
        thresh_str = f"{comp} metric {metric} threshold {thresh} {unit} action when exceeded {act_exc}"
        return f"{base_content}\n{thresh_str}"
        
    return base_content

def extract_entities_from_row(headers: List[str], row: List[str]) -> List[str]:
    """Extracts known entities (package names, metric names, thresholds) from row cell values."""
    entities = []
    ignored = {"*", "", "-", "none", "null", "default", "active"}
    for val in row:
        val_clean = val.strip()
        if val_clean.lower() not in ignored:
            entities.append(val_clean)
    return entities

# --- API Methods ---

def ingest_markdown_table(path: str, doc_meta: dict, db_path: Optional[str] = None) -> List[Node]:
    """Ingests a markdown table into the SQLite database.
    Performs validation and builds supersede chains.
    """
    db_file = db_path or str(DB_PATH)
    
    # Ensure parent dir exists
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Read Markdown content
    with open(path, "r", encoding="utf-8") as f:
        md_content = f.read()
        
    tables = parse_markdown_tables(md_content)
    if not tables:
        logger.warning(f"No tables found in markdown file at {path}")
        return []
        
    # For simplicity, ingest the first table found
    headers, rows = tables[0]
    doc_id = doc_meta["doc_id"]
    
    nodes_created = []
    
    conn = sqlite3.connect(db_file)
    try:
        init_db(conn)
        cursor = conn.cursor()
        
        for seq, row in enumerate(rows):
            # 1. Format content repeating headers
            content = format_node_content(headers, row)
            
            # 2. Compute IDs & hashes
            content_bytes = content.encode("utf-8")
            content_sha256 = hashlib.sha256(content_bytes).hexdigest()
            sha256_12 = content_sha256[:12]
            sha256_8 = content_sha256[:8]
            node_id = f"{doc_id}#{seq:03d}-{sha256_8}"
            
            # 3. Create Node Pydantic Model and validate
            node_dict = {
                "node_id": node_id,
                "doc_id": doc_id,
                "version": doc_meta.get("version"),
                "status": doc_meta.get("status", "active"),
                "domain": doc_meta.get("domain"),
                "authority_tier": doc_meta.get("authority_tier"),
                "layer": doc_meta.get("layer"),
                "namespace": doc_meta.get("namespace", "prod"),
                "conflict_flag": doc_meta.get("conflict_flag"),
                "effective_date": doc_meta.get("effective_date"),
                "sha256_12": sha256_12,
                "content": content,
                "chunk_seq": seq,
                "superseded_by": None
            }
            
            node = Node(**node_dict)
            
            # 4. Ingest/Save Vector (if enabled)
            vector_data = None
            embedding = get_embedding(content)
            if embedding:
                vector_data = vector_to_blob(embedding)
                
            # 5. Handle supersede chain
            cursor.execute(
                "SELECT node_id, content FROM nodes WHERE doc_id = ? AND chunk_seq = ? AND status = 'active'",
                (doc_id, seq)
            )
            existing = cursor.fetchone()
            if existing:
                old_node_id, old_content = existing
                if old_content != content:
                    # Content changed: supersede the old node
                    cursor.execute(
                        "UPDATE nodes SET status = 'superseded', superseded_by = ? WHERE node_id = ?",
                        (node_id, old_node_id)
                    )
                    
            # 6. Insert new node
            cursor.execute(
                """
                INSERT OR REPLACE INTO nodes (
                    node_id, doc_id, version, status, domain, authority_tier, layer, namespace,
                    conflict_flag, effective_date, sha256_12, content, superseded_by, chunk_seq, vector
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.node_id, node.doc_id, node.version, node.status, node.domain, node.authority_tier,
                    node.layer, node.namespace, node.conflict_flag, node.effective_date, node.sha256_12,
                    node.content, node.superseded_by, node.chunk_seq, vector_data
                )
            )
            
            # 7. Update FTS5 table
            # Clear older FTS5 row for this node_id if it exists to avoid duplication
            cursor.execute("DELETE FROM nodes_fts WHERE node_id = ?", (node.node_id,))
            cursor.execute(
                "INSERT INTO nodes_fts (node_id, content) VALUES (?, ?)",
                (node.node_id, node.content)
            )
            
            # 8. Build known_entities
            entities = extract_entities_from_row(headers, row)
            for entity in entities:
                cursor.execute(
                    "INSERT OR IGNORE INTO known_entities (entity) VALUES (?)",
                    (entity,)
                )
                
            nodes_created.append(node)
            
        conn.commit()
    finally:
        conn.close()
        
    return nodes_created

def search(query: str, namespace: str = "prod", db_path: Optional[str] = None, **filters) -> List[Node]:
    """Hybrid search executing FTS5 and optional Ollama embeddings, sorted by RRF or FTS5 score."""
    db_file = db_path or str(DB_PATH)
    if not Path(db_file).exists():
        return []
        
    conn = sqlite3.connect(db_file)
    try:
        cursor = conn.cursor()
        
        # Tokenize query for known entity check
        query_tokens = [t.strip() for t in re.findall(r'[a-zA-Z0-9_.-]+', query) if t.strip()]
        
        # Check known entities
        matched_entities = set()
        if query_tokens:
            placeholders = ",".join("?" for _ in query_tokens)
            cursor.execute(
                f"SELECT entity FROM known_entities WHERE LOWER(entity) IN ({placeholders})",
                [t.lower() for t in query_tokens]
            )
            for row in cursor.fetchall():
                matched_entities.add(row[0].lower())
                
        # Also check substring match for entities
        cursor.execute("SELECT entity FROM known_entities")
        all_entities = [row[0].lower() for row in cursor.fetchall()]
        for entity in all_entities:
            if entity in query.lower():
                matched_entities.add(entity)
                
        # Lexical FTS5 Search
        fts_nodes = []
        if query_tokens:
            def run_fts(fts_q: str):
                nodes = []
                sql_fts = """
                SELECT n.node_id, n.doc_id, n.version, n.status, n.domain, n.authority_tier, n.layer, n.namespace,
                       n.conflict_flag, n.effective_date, n.sha256_12, n.content, n.superseded_by, n.chunk_seq, n.vector
                FROM nodes n
                JOIN nodes_fts f ON n.node_id = f.node_id
                WHERE f.nodes_fts MATCH ?
                  AND n.namespace = ?
                """
                params_fts = [fts_q, namespace]
                
                # Apply filters (status defaults to 'active')
                status_filter = filters.get("status", "active")
                sql_fts += " AND n.status = ?"
                params_fts.append(status_filter)
                
                for k, v in filters.items():
                    if k == "status":
                        continue
                    sql_fts += f" AND n.{k} = ?"
                    params_fts.append(v)
                    
                sql_fts += " ORDER BY bm25(nodes_fts) ASC"
                
                cursor.execute(sql_fts, params_fts)
                for row in cursor.fetchall():
                    nodes.append(Node(
                        node_id=row[0], doc_id=row[1], version=row[2], status=row[3], domain=row[4],
                        authority_tier=row[5], layer=row[6], namespace=row[7], conflict_flag=row[8],
                        effective_date=row[9], sha256_12=row[10], content=row[11], superseded_by=row[12],
                        chunk_seq=row[13]
                    ))
                return nodes

            # Try AND first
            fts_query_and = " AND ".join(f'"{w}"' for w in query_tokens if w)
            fts_nodes = run_fts(fts_query_and)
            
            # Fallback to OR if no results
            if not fts_nodes:
                fts_query_or = " OR ".join(f'"{w}"' for w in query_tokens if w)
                fts_nodes = run_fts(fts_query_or)
                
        # Semantic Vector Search (if enabled)
        vector_nodes_sim = []
        query_vector = get_embedding(query)
        if query_vector:
            sql_vec = """
            SELECT node_id, doc_id, version, status, domain, authority_tier, layer, namespace,
                   conflict_flag, effective_date, sha256_12, content, superseded_by, chunk_seq, vector
            FROM nodes
            WHERE namespace = ?
            """
            params_vec = [namespace]
            
            status_filter = filters.get("status", "active")
            sql_vec += " AND status = ?"
            params_vec.append(status_filter)
            
            for k, v in filters.items():
                if k == "status":
                    continue
                sql_vec += f" AND {k} = ?"
                params_vec.append(v)
                
            cursor.execute(sql_vec, params_vec)
            for row in cursor.fetchall():
                node_vec_blob = row[14]
                if node_vec_blob:
                    node_vector = blob_to_vector(node_vec_blob)
                    sim = cosine_similarity(query_vector, node_vector)
                    node_obj = Node(
                        node_id=row[0], doc_id=row[1], version=row[2], status=row[3], domain=row[4],
                        authority_tier=row[5], layer=row[6], namespace=row[7], conflict_flag=row[8],
                        effective_date=row[9], sha256_12=row[10], content=row[11], superseded_by=row[12],
                        chunk_seq=row[13]
                    )
                    vector_nodes_sim.append((node_obj, sim))
                    
            # Sort by similarity descending
            vector_nodes_sim.sort(key=lambda x: x[1], reverse=True)
            
        # Merge via RRF if vector search yielded results, otherwise fallback to pure FTS5 results
        if query_vector and vector_nodes_sim:
            rrf_scores = {}
            node_map = {}
            
            for rank, node in enumerate(fts_nodes, start=1):
                node_map[node.node_id] = node
                rrf_scores[node.node_id] = rrf_scores.get(node.node_id, 0.0) + (1.0 / (60.0 + rank))
                
            for rank, (node, sim) in enumerate(vector_nodes_sim, start=1):
                node_map[node.node_id] = node
                rrf_scores[node.node_id] = rrf_scores.get(node.node_id, 0.0) + (1.0 / (60.0 + rank))
                
            sorted_ids = sorted(rrf_scores.keys(), key=lambda nid: rrf_scores[nid], reverse=True)
            final_nodes = [node_map[nid] for nid in sorted_ids]
        else:
            final_nodes = fts_nodes
            
        # Pin exact-match of known entities to head of the list (index 0)
        if matched_entities:
            pinned = []
            others = []
            for node in final_nodes:
                content_lower = node.content.lower()
                # Check if content contains any matched entity as substring or word
                if any(entity in content_lower for entity in matched_entities):
                    pinned.append(node)
                else:
                    others.append(node)
            final_nodes = pinned + others
            
        return final_nodes
    finally:
        conn.close()
