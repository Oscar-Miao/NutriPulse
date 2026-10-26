CREATE TABLE plan_session_instances (
  id TEXT PRIMARY KEY,
  enrollment_id TEXT NOT NULL REFERENCES user_plan_enrollments(id) ON DELETE CASCADE,
  plan_day_id TEXT NOT NULL REFERENCES plan_days(id),
  week_no INTEGER NOT NULL CHECK(week_no >= 1),
  day_no INTEGER NOT NULL CHECK(day_no BETWEEN 1 AND 7),
  scheduled_date TEXT NOT NULL,
  title TEXT NOT NULL,
  template_json TEXT NOT NULL,
  overrides_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK(status IN ('SCHEDULED','COMPLETED','PARTIAL')),
  completed_at TEXT,
  UNIQUE(enrollment_id, week_no, day_no),
  UNIQUE(enrollment_id, scheduled_date)
);
CREATE INDEX idx_plan_sessions_enrollment_date ON plan_session_instances(enrollment_id, scheduled_date);
ALTER TABLE workout_sessions ADD COLUMN plan_session_id TEXT REFERENCES plan_session_instances(id);
CREATE UNIQUE INDEX idx_workouts_plan_session ON workout_sessions(plan_session_id)
  WHERE plan_session_id IS NOT NULL;
