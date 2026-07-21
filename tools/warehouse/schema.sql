-- Schema for warehouse.db

CREATE TABLE IF NOT EXISTS indexed_files (
    file_path TEXT PRIMARY KEY,
    file_hash TEXT NOT NULL,        -- SHA-256 hash of physical file
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,      -- Format: [file_name]#[page]#[chunk_seq]
    file_path TEXT NOT NULL,
    specialty TEXT NOT NULL,
    page INTEGER NOT NULL,          -- 1-based page number
    char_span TEXT NOT NULL,        -- e.g. "0-500"
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL,     -- SHA-256 of text content
    authority_tier TEXT NOT NULL,   -- T1, T2, T3
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    vector BLOB                     -- Serialized float32 embeddings
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    text
);
