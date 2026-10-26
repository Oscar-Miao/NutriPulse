-- A stopped enrollment keeps its historical schedule. Record the effective
-- stop day so habit reports do not count future, cancelled plan sessions.
ALTER TABLE user_plan_enrollments ADD COLUMN stopped_on TEXT;
CREATE INDEX idx_plan_enrollment_user_stop
    ON user_plan_enrollments(user_id,status,stopped_on);
