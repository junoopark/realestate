-- Qualitative content schema. Equivalent to backend/app/db/models.py.
-- Run as the database owner. FastAPI also creates these tables at startup.
-- These tables have no anonymous/public REST policies; access goes through FastAPI.
CREATE TABLE IF NOT EXISTS content_snapshots (
    key VARCHAR(40) PRIMARY KEY,
    content JSON NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    updated_at VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS policy_source_states (
    id VARCHAR(50) PRIMARY KEY,
    last_checked_at VARCHAR(40),
    last_success_at VARCHAR(40),
    status VARCHAR(30) NOT NULL DEFAULT 'never_collected',
    error TEXT,
    item_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS policy_documents (
    id VARCHAR(64) PRIMARY KEY,
    source_id VARCHAR(50) NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    agency VARCHAR(100) NOT NULL,
    published_at VARCHAR(40),
    summary TEXT NOT NULL,
    category VARCHAR(40) NOT NULL,
    matched_keywords JSON NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    first_seen_at VARCHAR(40) NOT NULL,
    last_seen_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_policy_documents_source_id ON policy_documents(source_id);
CREATE INDEX IF NOT EXISTS ix_policy_documents_published_at ON policy_documents(published_at);
CREATE TABLE IF NOT EXISTS policy_document_versions (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES policy_documents(id),
    revision INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    content JSON NOT NULL,
    observed_at VARCHAR(40) NOT NULL,
    UNIQUE(document_id, revision)
);
CREATE INDEX IF NOT EXISTS ix_policy_document_versions_document_id ON policy_document_versions(document_id);
ALTER TABLE content_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_source_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_document_versions ENABLE ROW LEVEL SECURITY;
