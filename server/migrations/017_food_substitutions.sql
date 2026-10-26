-- Curated ingredient alternatives for self-cook recipe previews. Suggestions
-- are not automatically applied to accepted meals.
CREATE TABLE food_substitutions (
  from_food_id TEXT NOT NULL REFERENCES food_items(id) ON DELETE CASCADE,
  to_food_id TEXT NOT NULL REFERENCES food_items(id) ON DELETE CASCADE,
  basis TEXT NOT NULL DEFAULT 'kcal_equivalent'
    CHECK(basis = 'kcal_equivalent'),
  rank INTEGER NOT NULL DEFAULT 1 CHECK(rank > 0),
  source TEXT NOT NULL DEFAULT 'demo-curated-v1',
  PRIMARY KEY(from_food_id, to_food_id),
  CHECK(from_food_id <> to_food_id)
);
CREATE INDEX idx_food_substitutions_from_rank
  ON food_substitutions(from_food_id, rank);
