import os
import struct
import math
import logging
import httpx
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
    """Fetches bge-m3 embedding using Ollama API with fallback endpoints."""
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    
    # Try /api/embeddings endpoint first
    embeddings_url = f"{ollama_base}/api/embeddings"
    try:
        response = httpx.post(
            embeddings_url,
            json={"model": "bge-m3", "prompt": text},
            timeout=10.0
        )
        if response.status_code == 200:
            embedding = response.json().get("embedding")
            if embedding:
                return embedding
    except Exception as e:
        logger.warning(f"Ollama /api/embeddings failed: {e}. Trying fallback /api/embed.")

    # Fallback to /api/embed endpoint
    embed_url = f"{ollama_base}/api/embed"
    try:
        response = httpx.post(
            embed_url,
            json={"model": "bge-m3", "input": text},
            timeout=10.0
        )
        if response.status_code == 200:
            embeddings = response.json().get("embeddings")
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
    except Exception as e:
        logger.warning(f"Ollama fallback /api/embed failed: {e}.")
        
    return None
