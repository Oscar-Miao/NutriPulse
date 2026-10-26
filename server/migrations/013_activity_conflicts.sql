ALTER TABLE sync_conflicts ADD COLUMN overlap_seconds REAL NOT NULL DEFAULT 0;
ALTER TABLE device_samples ADD COLUMN pending_activation INTEGER NOT NULL DEFAULT 0
  CHECK(pending_activation IN (0,1,2));
CREATE UNIQUE INDEX idx_sync_conflict_pair ON sync_conflicts(sample_id,domain_record_id)
  WHERE reason='TIME_OVERLAP';
CREATE INDEX idx_sync_conflict_pending ON sync_conflicts(user_id,resolution,reason);
CREATE INDEX idx_device_activity_window ON device_samples(local_date,sample_type,end_at);
