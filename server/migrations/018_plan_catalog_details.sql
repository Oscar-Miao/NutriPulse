ALTER TABLE training_plans ADD COLUMN suitability TEXT NOT NULL DEFAULT '';
ALTER TABLE training_plans ADD COLUMN contraindications TEXT NOT NULL DEFAULT '';
ALTER TABLE training_plans ADD COLUMN warmup TEXT NOT NULL DEFAULT '';
ALTER TABLE training_plans ADD COLUMN cooldown TEXT NOT NULL DEFAULT '';
ALTER TABLE training_plans ADD COLUMN progression_rule TEXT NOT NULL DEFAULT '';
ALTER TABLE training_plans ADD COLUMN alternatives_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE training_plans ADD COLUMN estimated_minutes INTEGER NOT NULL DEFAULT 45;
ALTER TABLE training_plans ADD COLUMN completion_rule TEXT NOT NULL DEFAULT '';

CREATE TABLE official_plan_template_history (
  plan_id TEXT NOT NULL REFERENCES training_plans(id),
  version INTEGER NOT NULL,
  plan_day_id TEXT NOT NULL REFERENCES plan_days(id),
  week_no INTEGER NOT NULL,
  day_no INTEGER NOT NULL,
  title TEXT NOT NULL,
  session_template_json TEXT NOT NULL,
  PRIMARY KEY(plan_id, version, week_no, day_no)
);
