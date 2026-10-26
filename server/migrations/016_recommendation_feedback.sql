-- Per-recipe soft feedback changes ranking only; it is never an allergy or
-- permanent dietary restriction. One current opinion per local user/recipe.
CREATE TABLE recommendation_feedback (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  recipe_id TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  source_item_id TEXT REFERENCES recommendation_items(id) ON DELETE SET NULL,
  feedback_type TEXT NOT NULL CHECK(feedback_type IN ('DISLIKE','REPEATED','UNSUITABLE')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, recipe_id)
);
CREATE INDEX idx_recommendation_feedback_user_type
  ON recommendation_feedback(user_id, feedback_type);
