-- Adds persisted meal-decision constraints without changing historical logs.
CREATE TABLE dining_preferences (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  max_cost_cny REAL CHECK(max_cost_cny IS NULL OR max_cost_cny BETWEEN 1 AND 1000),
  max_cook_minutes INTEGER CHECK(max_cook_minutes IS NULL OR max_cook_minutes BETWEEN 5 AND 240),
  flavor_codes_json TEXT NOT NULL DEFAULT '[]',
  preferred_scenario TEXT NOT NULL DEFAULT 'self_cook'
    CHECK(preferred_scenario IN ('self_cook','takeout','dine_in','convenience')),
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE recipes ADD COLUMN estimated_cost_cny REAL
  CHECK(estimated_cost_cny IS NULL OR estimated_cost_cny >= 0);
ALTER TABLE recipes ADD COLUMN flavors_json TEXT NOT NULL DEFAULT '[]';
