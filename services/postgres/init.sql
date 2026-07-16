CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS documents (
    id              BIGSERIAL PRIMARY KEY,
    file_path       TEXT UNIQUE NOT NULL,
    file_name       TEXT NOT NULL,
    file_ext        TEXT,
    file_size       BIGINT DEFAULT 0,
    file_hash       TEXT,
    content_text    TEXT,
    content_html    TEXT,
    page_count      INT DEFAULT 0,
    char_count      INT DEFAULT 0,
    is_encrypted    BOOLEAN DEFAULT FALSE,
    is_processed    BOOLEAN DEFAULT FALSE,
    parse_error     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doc_vectors (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT DEFAULT 0,
    chunk_text  TEXT NOT NULL,
    embedding   vector(1024),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doc_categories (
    id              BIGSERIAL PRIMARY KEY,
    doc_id          BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    category        TEXT NOT NULL,
    sub_category    TEXT,
    tags            TEXT[],
    confidence      REAL DEFAULT 0.0,
    summary         TEXT,
    key_points      JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doc_relations (
    id              BIGSERIAL PRIMARY KEY,
    doc_id_a        BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    doc_id_b        BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    relation_type   TEXT NOT NULL DEFAULT 'similar',
    similarity_score REAL DEFAULT 0.0,
    merge_status    TEXT DEFAULT 'pending',
    merged_doc_id   BIGINT REFERENCES documents(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS search_log (
    id          BIGSERIAL PRIMARY KEY,
    query_text  TEXT NOT NULL,
    search_type TEXT DEFAULT 'fulltext',
    result_ids  BIGINT[],
    result_count INT DEFAULT 0,
    latency_ms  INT DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_file_ext ON documents(file_ext);
CREATE INDEX IF NOT EXISTS idx_documents_is_processed ON documents(is_processed);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_doc_categories_category ON doc_categories(category);
CREATE INDEX IF NOT EXISTS idx_doc_vectors_embedding ON doc_vectors USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_documents_content_fts ON documents USING gin(to_tsvector('simple', coalesce(left(content_text, 200000), ')));
CREATE INDEX IF NOT EXISTS idx_doc_relations_similarity ON doc_relations(similarity_score DESC);
