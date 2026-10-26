CREATE TABLE users (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL DEFAULT '我',
  timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  locale TEXT NOT NULL DEFAULT 'zh-CN',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  birth_date TEXT,
  formula_sex TEXT CHECK(formula_sex IN ('male','female')),
  height_cm REAL CHECK(height_cm BETWEEN 100 AND 230),
  activity_level TEXT NOT NULL DEFAULT 'light',
  profile_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE body_measurements (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  measured_at TEXT NOT NULL,
  weight_kg REAL NOT NULL CHECK(weight_kg BETWEEN 25 AND 350),
  body_fat_pct REAL CHECK(body_fat_pct BETWEEN 0 AND 100),
  waist_cm REAL,
  source_type TEXT NOT NULL DEFAULT 'manual',
  device_sample_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_measurements_user_time ON body_measurements(user_id, measured_at DESC);
CREATE TABLE goals (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  goal_type TEXT NOT NULL CHECK(goal_type IN ('fat_loss','maintenance','muscle_gain','recovery')),
  start_date TEXT NOT NULL,
  end_date TEXT,
  target_weight_kg REAL,
  calorie_adjustment REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX uq_active_goal ON goals(user_id) WHERE status='ACTIVE';
CREATE TABLE nutrition_targets (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  kcal REAL NOT NULL,
  bmr_kcal REAL NOT NULL,
  tdee_kcal REAL NOT NULL,
  carb_g REAL NOT NULL,
  protein_g REAL NOT NULL,
  fat_g REAL NOT NULL,
  fiber_g REAL NOT NULL DEFAULT 25,
  water_ml INTEGER NOT NULL DEFAULT 2400,
  algorithm_version TEXT NOT NULL,
  locked_fields_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_target_effective ON nutrition_targets(user_id, effective_from DESC);
CREATE TABLE user_allergies (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  allergen_code TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'avoid',
  notes TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id, allergen_code)
);
CREATE TABLE user_dietary_restrictions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  restriction_code TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'avoid',
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id, restriction_code)
);
CREATE TABLE user_preferences (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  value_code TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1 CHECK(weight BETWEEN -1 AND 1),
  source TEXT NOT NULL DEFAULT 'user',
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id, category, value_code)
);
CREATE TABLE training_profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  level TEXT NOT NULL DEFAULT 'beginner',
  days_per_week INTEGER NOT NULL DEFAULT 3,
  session_minutes INTEGER NOT NULL DEFAULT 45,
  equipment_json TEXT NOT NULL DEFAULT '[]',
  limitations_json TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE food_items (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  brand TEXT,
  barcode TEXT UNIQUE,
  base_amount REAL NOT NULL DEFAULT 100,
  base_unit TEXT NOT NULL DEFAULT 'g',
  kcal REAL NOT NULL CHECK(kcal >= 0),
  carb_g REAL NOT NULL DEFAULT 0,
  protein_g REAL NOT NULL DEFAULT 0,
  fat_g REAL NOT NULL DEFAULT 0,
  fiber_g REAL NOT NULL DEFAULT 0,
  allergens_json TEXT NOT NULL DEFAULT '[]',
  data_source TEXT NOT NULL DEFAULT 'local',
  version INTEGER NOT NULL DEFAULT 1,
  verified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE food_aliases (
  id TEXT PRIMARY KEY,
  food_id TEXT NOT NULL REFERENCES food_items(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  locale TEXT NOT NULL DEFAULT 'zh-CN'
);
CREATE INDEX idx_food_name ON food_items(name);
CREATE TABLE recipes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  servings REAL NOT NULL DEFAULT 1,
  instructions_json TEXT NOT NULL DEFAULT '[]',
  prep_minutes INTEGER NOT NULL DEFAULT 0,
  cook_minutes INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'official',
  scenario TEXT NOT NULL DEFAULT 'self_cook',
  goal_types_json TEXT NOT NULL DEFAULT '[]',
  allergens_json TEXT NOT NULL DEFAULT '[]',
  version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE recipe_ingredients (
  recipe_id TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  food_id TEXT NOT NULL REFERENCES food_items(id),
  amount REAL NOT NULL,
  unit TEXT NOT NULL DEFAULT 'g',
  grams REAL,
  optional INTEGER NOT NULL DEFAULT 0,
  substitution_group TEXT,
  PRIMARY KEY(recipe_id, food_id)
);
CREATE TABLE meals (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  local_date TEXT NOT NULL,
  meal_type TEXT NOT NULL CHECK(meal_type IN ('breakfast','lunch','dinner','snack')),
  status TEXT NOT NULL CHECK(status IN ('DRAFT','PLANNED','CONSUMED','ARCHIVED')),
  planned_at TEXT,
  consumed_at TEXT,
  source_type TEXT NOT NULL DEFAULT 'manual',
  source_ref_id TEXT,
  idempotency_key TEXT UNIQUE,
  note TEXT,
  deleted_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_meals_user_day ON meals(user_id, local_date, status);
CREATE TABLE meal_items (
  id TEXT PRIMARY KEY,
  meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
  food_id TEXT REFERENCES food_items(id),
  display_name TEXT NOT NULL,
  amount REAL NOT NULL CHECK(amount > 0),
  unit TEXT NOT NULL,
  grams REAL,
  kcal REAL NOT NULL CHECK(kcal >= 0),
  carb_g REAL NOT NULL DEFAULT 0,
  protein_g REAL NOT NULL DEFAULT 0,
  fat_g REAL NOT NULL DEFAULT 0,
  fiber_g REAL NOT NULL DEFAULT 0,
  allergens_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL CHECK(confidence BETWEEN 0 AND 1),
  user_edited INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_meal_items_meal ON meal_items(meal_id);
CREATE TABLE water_logs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  occurred_at TEXT NOT NULL,
  local_date TEXT NOT NULL,
  amount_ml INTEGER NOT NULL CHECK(amount_ml > 0),
  source_type TEXT NOT NULL DEFAULT 'manual',
  idempotency_key TEXT UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE media_assets (
  id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  retention_until TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE food_scan_jobs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  media_id TEXT REFERENCES media_assets(id),
  status TEXT NOT NULL,
  result_json TEXT,
  error_code TEXT,
  model_version TEXT,
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE exercises (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  muscle_groups_json TEXT NOT NULL DEFAULT '[]',
  equipment TEXT,
  met_default REAL,
  instructions_json TEXT NOT NULL DEFAULT '[]',
  version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE training_plans (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  level TEXT NOT NULL,
  goal_type TEXT NOT NULL,
  weeks INTEGER NOT NULL,
  days_per_week INTEGER NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PUBLISHED',
  version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE plan_days (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES training_plans(id) ON DELETE CASCADE,
  week_no INTEGER NOT NULL,
  day_no INTEGER NOT NULL,
  title TEXT NOT NULL,
  session_template_json TEXT NOT NULL,
  UNIQUE(plan_id, week_no, day_no)
);
CREATE TABLE user_plan_enrollments (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id TEXT NOT NULL REFERENCES training_plans(id),
  plan_version INTEGER NOT NULL,
  start_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  settings_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE workout_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  local_date TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT,
  workout_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'COMPLETED',
  minutes REAL NOT NULL DEFAULT 0,
  met_value REAL,
  kcal REAL NOT NULL DEFAULT 0,
  kcal_source TEXT NOT NULL DEFAULT 'MET',
  plan_instance_id TEXT REFERENCES user_plan_enrollments(id),
  idempotency_key TEXT UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_workouts_user_day ON workout_sessions(user_id, local_date, status);
CREATE TABLE exercise_sets (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
  exercise_id TEXT REFERENCES exercises(id),
  exercise_name TEXT NOT NULL,
  set_no INTEGER NOT NULL,
  weight_kg REAL,
  reps INTEGER,
  duration_sec INTEGER,
  distance_m REAL,
  rpe REAL,
  rir REAL,
  completed_at TEXT,
  volume REAL NOT NULL DEFAULT 0,
  UNIQUE(session_id, exercise_name, set_no)
);
CREATE TABLE device_connections (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  external_user_ref TEXT,
  scopes_json TEXT NOT NULL DEFAULT '[]',
  token_ref TEXT,
  sync_cursor TEXT,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  last_synced_at TEXT
);
CREATE TABLE device_samples (
  id TEXT PRIMARY KEY,
  connection_id TEXT NOT NULL REFERENCES device_connections(id) ON DELETE CASCADE,
  external_id TEXT NOT NULL,
  sample_type TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT,
  local_date TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  raw_hash TEXT,
  import_batch_id TEXT,
  UNIQUE(connection_id, external_id)
);
CREATE INDEX idx_device_samples_day ON device_samples(connection_id, local_date, sample_type);
CREATE TABLE sync_conflicts (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  sample_id TEXT NOT NULL REFERENCES device_samples(id),
  domain_record_id TEXT,
  reason TEXT NOT NULL,
  resolution TEXT,
  resolved_at TEXT
);
CREATE TABLE daily_energy_snapshots (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  local_date TEXT NOT NULL,
  target_id TEXT REFERENCES nutrition_targets(id),
  intake_kcal REAL NOT NULL DEFAULT 0,
  bmr_kcal REAL NOT NULL DEFAULT 0,
  tdee_kcal REAL NOT NULL DEFAULT 0,
  activity_kcal REAL NOT NULL DEFAULT 0,
  net_kcal REAL NOT NULL DEFAULT 0,
  macro_json TEXT NOT NULL DEFAULT '{}',
  completeness TEXT NOT NULL DEFAULT 'partial',
  calc_version TEXT NOT NULL DEFAULT 'energy-v1',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, local_date)
);
CREATE TABLE recommendation_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  local_date TEXT NOT NULL,
  meal_type TEXT NOT NULL,
  context_snapshot_json TEXT NOT NULL,
  constraint_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PRESENTED',
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE recommendation_items (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES recommendation_sessions(id) ON DELETE CASCADE,
  candidate_type TEXT NOT NULL,
  candidate_ref_id TEXT,
  title TEXT NOT NULL,
  nutrition_json TEXT NOT NULL,
  score REAL NOT NULL,
  reason_json TEXT NOT NULL,
  modification_json TEXT NOT NULL DEFAULT '[]',
  rank INTEGER NOT NULL,
  accepted_at TEXT
);
CREATE TABLE chat_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  profile_version INTEGER,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ended_at TEXT
);
CREATE TABLE chat_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content_redacted TEXT NOT NULL,
  structured_payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE agent_runs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  agent_type TEXT NOT NULL,
  provider TEXT,
  model TEXT,
  prompt_version TEXT NOT NULL,
  input_hash TEXT,
  output_json TEXT,
  status TEXT NOT NULL,
  latency_ms INTEGER,
  token_usage_json TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE diagnostic_reports (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  metrics_snapshot_json TEXT NOT NULL,
  agent_run_id TEXT REFERENCES agent_runs(id),
  content_json TEXT NOT NULL,
  confidence REAL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE articles (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  cover_url TEXT,
  published_at TEXT,
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT,
  status TEXT NOT NULL DEFAULT 'VISIBLE',
  content_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX idx_articles_visible ON articles(status, published_at DESC);
CREATE TABLE outbox_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING',
  retry_count INTEGER NOT NULL DEFAULT 0,
  next_retry_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE background_jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0,
  run_after TEXT,
  locked_at TEXT,
  last_error TEXT
);
CREATE TABLE audit_logs (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id),
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  before_hash TEXT,
  after_hash TEXT,
  request_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO users(id, display_name) VALUES ('local-user', '我');
INSERT INTO profiles(user_id) VALUES ('local-user');
INSERT INTO training_profiles(user_id) VALUES ('local-user');
