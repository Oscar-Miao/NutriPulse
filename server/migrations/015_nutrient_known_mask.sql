-- Existing rows have no reliable field-presence provenance. Keep them
-- conservatively unknown rather than inferring that stored zeros were entered.
ALTER TABLE meal_items ADD COLUMN nutrient_known_mask INTEGER NOT NULL DEFAULT 0
  CHECK(nutrient_known_mask BETWEEN 0 AND 15);
