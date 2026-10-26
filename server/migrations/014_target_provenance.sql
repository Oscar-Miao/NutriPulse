ALTER TABLE nutrition_targets ADD COLUMN input_snapshot_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE nutrition_targets ADD COLUMN goal_id TEXT;
ALTER TABLE nutrition_targets ADD COLUMN measurement_id TEXT;
ALTER TABLE nutrition_targets ADD COLUMN profile_version INTEGER;
