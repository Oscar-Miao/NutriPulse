ALTER TABLE workout_sessions ADD COLUMN intensity TEXT;
ALTER TABLE workout_sessions ADD COLUMN calculation_version TEXT NOT NULL DEFAULT 'legacy-unversioned';
ALTER TABLE training_profiles ADD COLUMN active_kcal_goal INTEGER NOT NULL DEFAULT 300
  CHECK(active_kcal_goal BETWEEN 50 AND 2000);
