ALTER TABLE food_scan_jobs ADD COLUMN idempotency_key TEXT;
ALTER TABLE food_scan_jobs ADD COLUMN input_hash TEXT;
ALTER TABLE food_scan_jobs ADD COLUMN attempt_id TEXT;
ALTER TABLE food_scan_jobs ADD COLUMN processing_started_at TEXT;

CREATE UNIQUE INDEX idx_food_scan_idempotency
  ON food_scan_jobs(user_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
