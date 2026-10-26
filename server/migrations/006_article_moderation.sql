ALTER TABLE articles ADD COLUMN priority INTEGER NOT NULL DEFAULT 0 CHECK(priority BETWEEN 0 AND 100);
CREATE INDEX idx_articles_home ON articles(status, priority DESC, published_at DESC);
