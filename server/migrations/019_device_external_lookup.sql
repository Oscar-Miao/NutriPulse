-- Cross-connection source-ID deduplication needs to find every historical
-- copy of a candidate record, including copies whose local date was revised.
CREATE INDEX IF NOT EXISTS idx_device_samples_external_type
    ON device_samples(external_id,sample_type);
