ALTER TABLE daily_energy_snapshots ADD COLUMN expenditure_kcal REAL NOT NULL DEFAULT 0;
ALTER TABLE daily_energy_snapshots ADD COLUMN water_ml INTEGER NOT NULL DEFAULT 0;
ALTER TABLE daily_energy_snapshots ADD COLUMN workout_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE daily_energy_snapshots ADD COLUMN training_volume REAL NOT NULL DEFAULT 0;

-- Source-table triggers keep the analytics cache independent from callers.
-- INSERT and DELETE evict one local day; UPDATE evicts old and new local days.
CREATE TRIGGER energy_cache_meal_ai AFTER INSERT ON meals BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=NEW.user_id AND local_date=NEW.local_date;
END;
CREATE TRIGGER energy_cache_meal_au AFTER UPDATE ON meals BEGIN
  DELETE FROM daily_energy_snapshots WHERE (user_id=OLD.user_id AND local_date=OLD.local_date)
    OR (user_id=NEW.user_id AND local_date=NEW.local_date);
END;
CREATE TRIGGER energy_cache_meal_ad AFTER DELETE ON meals BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=OLD.user_id AND local_date=OLD.local_date;
END;

CREATE TRIGGER energy_cache_item_ai AFTER INSERT ON meal_items BEGIN
  DELETE FROM daily_energy_snapshots WHERE EXISTS (SELECT 1 FROM meals m WHERE m.id=NEW.meal_id
    AND m.user_id=daily_energy_snapshots.user_id AND m.local_date=daily_energy_snapshots.local_date);
END;
CREATE TRIGGER energy_cache_item_au AFTER UPDATE ON meal_items BEGIN
  DELETE FROM daily_energy_snapshots WHERE EXISTS (SELECT 1 FROM meals m
    WHERE m.id IN (OLD.meal_id,NEW.meal_id) AND m.user_id=daily_energy_snapshots.user_id
      AND m.local_date=daily_energy_snapshots.local_date);
END;
CREATE TRIGGER energy_cache_item_ad AFTER DELETE ON meal_items BEGIN
  DELETE FROM daily_energy_snapshots WHERE EXISTS (SELECT 1 FROM meals m WHERE m.id=OLD.meal_id
    AND m.user_id=daily_energy_snapshots.user_id AND m.local_date=daily_energy_snapshots.local_date);
END;

CREATE TRIGGER energy_cache_water_ai AFTER INSERT ON water_logs BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=NEW.user_id AND local_date=NEW.local_date;
END;
CREATE TRIGGER energy_cache_water_au AFTER UPDATE ON water_logs BEGIN
  DELETE FROM daily_energy_snapshots WHERE (user_id=OLD.user_id AND local_date=OLD.local_date)
    OR (user_id=NEW.user_id AND local_date=NEW.local_date);
END;
CREATE TRIGGER energy_cache_water_ad AFTER DELETE ON water_logs BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=OLD.user_id AND local_date=OLD.local_date;
END;

CREATE TRIGGER energy_cache_workout_ai AFTER INSERT ON workout_sessions BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=NEW.user_id AND local_date=NEW.local_date;
END;
CREATE TRIGGER energy_cache_workout_au AFTER UPDATE ON workout_sessions BEGIN
  DELETE FROM daily_energy_snapshots WHERE (user_id=OLD.user_id AND local_date=OLD.local_date)
    OR (user_id=NEW.user_id AND local_date=NEW.local_date);
END;
CREATE TRIGGER energy_cache_workout_ad AFTER DELETE ON workout_sessions BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=OLD.user_id AND local_date=OLD.local_date;
END;

CREATE TRIGGER energy_cache_set_ai AFTER INSERT ON exercise_sets BEGIN
  DELETE FROM daily_energy_snapshots WHERE EXISTS (SELECT 1 FROM workout_sessions w
    WHERE w.id=NEW.session_id AND w.user_id=daily_energy_snapshots.user_id
      AND w.local_date=daily_energy_snapshots.local_date);
END;
CREATE TRIGGER energy_cache_set_au AFTER UPDATE ON exercise_sets BEGIN
  DELETE FROM daily_energy_snapshots WHERE EXISTS (SELECT 1 FROM workout_sessions w
    WHERE w.id IN (OLD.session_id,NEW.session_id) AND w.user_id=daily_energy_snapshots.user_id
      AND w.local_date=daily_energy_snapshots.local_date);
END;
CREATE TRIGGER energy_cache_set_ad AFTER DELETE ON exercise_sets BEGIN
  DELETE FROM daily_energy_snapshots WHERE EXISTS (SELECT 1 FROM workout_sessions w
    WHERE w.id=OLD.session_id AND w.user_id=daily_energy_snapshots.user_id
      AND w.local_date=daily_energy_snapshots.local_date);
END;

CREATE TRIGGER energy_cache_sample_ai AFTER INSERT ON device_samples BEGIN
  DELETE FROM daily_energy_snapshots WHERE local_date=NEW.local_date AND user_id=(
    SELECT user_id FROM device_connections WHERE id=NEW.connection_id);
END;
CREATE TRIGGER energy_cache_sample_au AFTER UPDATE ON device_samples BEGIN
  DELETE FROM daily_energy_snapshots WHERE (local_date=OLD.local_date AND user_id=(
    SELECT user_id FROM device_connections WHERE id=OLD.connection_id))
    OR (local_date=NEW.local_date AND user_id=(
    SELECT user_id FROM device_connections WHERE id=NEW.connection_id));
END;
CREATE TRIGGER energy_cache_sample_ad AFTER DELETE ON device_samples BEGIN
  DELETE FROM daily_energy_snapshots WHERE local_date=OLD.local_date AND user_id=(
    SELECT user_id FROM device_connections WHERE id=OLD.connection_id);
END;
-- Cursor/time updates do not affect energy. Revocation or provider changes do.
CREATE TRIGGER energy_cache_connection_au AFTER UPDATE OF status,provider,user_id ON device_connections BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id IN (OLD.user_id,NEW.user_id);
END;
CREATE TRIGGER energy_cache_connection_bd BEFORE DELETE ON device_connections BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=OLD.user_id;
END;

-- Remove referencing cache rows before a target is replaced or deleted.
CREATE TRIGGER energy_cache_target_ai AFTER INSERT ON nutrition_targets BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=NEW.user_id AND local_date>=NEW.effective_from
    AND (NEW.effective_to IS NULL OR local_date<=NEW.effective_to);
END;
CREATE TRIGGER energy_cache_target_bu BEFORE UPDATE ON nutrition_targets BEGIN
  DELETE FROM daily_energy_snapshots WHERE (user_id=OLD.user_id AND local_date>=OLD.effective_from
    AND (OLD.effective_to IS NULL OR local_date<=OLD.effective_to))
    OR (user_id=NEW.user_id AND local_date>=NEW.effective_from
    AND (NEW.effective_to IS NULL OR local_date<=NEW.effective_to));
END;
CREATE TRIGGER energy_cache_target_bd BEFORE DELETE ON nutrition_targets BEGIN
  DELETE FROM daily_energy_snapshots WHERE user_id=OLD.user_id AND local_date>=OLD.effective_from
    AND (OLD.effective_to IS NULL OR local_date<=OLD.effective_to);
END;
