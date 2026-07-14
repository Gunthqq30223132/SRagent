import os
import struct
import math
import logging
import httpx
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

def vector_to_blob(vector: List[float]) -> bytes:
    """Serializes a list of floats to a float32 binary BLOB."""
    if not vector:
        return b""
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

def get_bge_embedding(text: str) -> Optional[List[float]]:
    """Fetches bge-m3 embedding using Ollama API with fallback endpoints and retries."""
    results = get_bge_embeddings_batch([text])
    if results and len(results) > 0:
        return results[0]
    return None

def get_bge_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """Fetches bge-m3 embeddings in batch using Ollama API /api/embed with retries.
    Falls back to single requests if batch endpoint fails.
    """
    if not texts:
        return []
        
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    embed_url = f"{ollama_base}/api/embed"
    embeddings_url = f"{ollama_base}/api/embeddings"
    
    max_retries = 3
    
    # 1. Try Batch /api/embed first with retries
    for attempt in range(max_retries):
        try:
            response = httpx.post(
                embed_url,
                json={"model": "bge-m3", "input": texts},
                timeout=30.0
            )
            if response.status_code == 200:
                embeddings = response.json().get("embeddings")
                if embeddings and len(embeddings) == len(texts):
                    return embeddings
        except Exception as e:
            logger.warning(f"Ollama batch /api/embed attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2.0 ** attempt)
                
    # 2. Fallback: single requests for each text in batch
    results = []
    for text in texts:
        vector = None
        for attempt in range(max_retries):
            # Try /api/embeddings
            try:
                response = httpx.post(
                    embeddings_url,
                    json={"model": "bge-m3", "prompt": text},
                    timeout=15.0
                )
                if response.status_code == 200:
                    embedding = response.json().get("embedding")
                    if embedding:
                        vector = embedding
                        break
            except Exception as e:
                logger.warning(f"Ollama single /api/embeddings attempt {attempt+1} failed: {e}")
                
            # Try /api/embed single
            try:
                response = httpx.post(
                    embed_url,
                    json={"model": "bge-m3", "input": text},
                    timeout=15.0
                )
                if response.status_code == 200:
                    embeddings = response.json().get("embeddings")
                    if embeddings and len(embeddings) > 0:
                        vector = embeddings[0]
                        break
            except Exception as e:
                logger.warning(f"Ollama single /api/embed attempt {attempt+1} failed: {e}")
                
            if attempt < max_retries - 1:
                time.sleep(1.0)
        results.append(vector)
        
    return results
