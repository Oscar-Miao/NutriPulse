ALTER TABLE diagnostic_reports ADD COLUMN model_name TEXT NOT NULL DEFAULT 'rules-v1';
ALTER TABLE diagnostic_reports ADD COLUMN prompt_version TEXT NOT NULL DEFAULT 'rule-diagnosis.v1';
ALTER TABLE diagnostic_reports ADD COLUMN input_hash TEXT;
CREATE INDEX idx_diagnostic_period_versions
  ON diagnostic_reports(user_id, period_start, period_end, version DESC);
