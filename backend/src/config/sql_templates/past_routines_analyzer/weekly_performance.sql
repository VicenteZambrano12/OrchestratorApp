-- All sets of every workout the user logged during the last 7 full days
-- (today and the 6 previous calendar days). No routing parameters; only the
-- session's :user_id (INTEGER) scopes the data.
SELECT
    DATE(f.created_at) AS training_date,
    f.training_id,
    r.name AS training_day,
    f.exercise_order,
    e.name AS exercise_name,
    e.primary_muscle,
    f.set_number,
    f.reps,
    f.weight,
    u.weight_unit,
    f.duration_seconds,
    f.distance_meters,
    f.rpe
FROM fact_workout_sets AS f
JOIN dim_routines AS r ON r.id = f.routine_id
JOIN dim_exercises AS e ON e.id = f.exercise_id
JOIN dim_users AS u ON u.id = f.user_id
WHERE f.user_id = :user_id
  AND f.training_id IS NOT NULL
  AND DATE(f.created_at) >= DATE('now', 'localtime', '-6 days')
  AND DATE(f.created_at) <= DATE('now', 'localtime')
ORDER BY training_date, f.training_id, f.exercise_order, f.set_number;
