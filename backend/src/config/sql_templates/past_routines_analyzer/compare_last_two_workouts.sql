-- Sets of the user's two most recent logged workouts whose routine (training
-- day) name fuzzily matches :day_type, for side-by-side comparison.
-- training_rank = 1 is the latest workout, 2 the one before it.
-- Params: :user_id (INTEGER), :day_type (TEXT lowercase keyword, or NULL to
-- match any training day).
WITH ranked_trainings AS (
    SELECT
        f.training_id,
        ROW_NUMBER() OVER (
            ORDER BY MAX(f.created_at) DESC, MAX(f.id) DESC
        ) AS training_rank
    FROM fact_workout_sets AS f
    JOIN dim_routines AS r ON r.id = f.routine_id
    WHERE f.user_id = :user_id
      AND f.training_id IS NOT NULL
      AND (
          :day_type IS NULL
          OR LOWER(r.name) LIKE '%' || LOWER(TRIM(:day_type)) || '%'
      )
    GROUP BY f.training_id
)
SELECT
    t.training_rank,
    f.training_id,
    DATE(f.created_at) AS training_date,
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
JOIN ranked_trainings AS t ON t.training_id = f.training_id
JOIN dim_routines AS r ON r.id = f.routine_id
JOIN dim_exercises AS e ON e.id = f.exercise_id
JOIN dim_users AS u ON u.id = f.user_id
WHERE f.user_id = :user_id
  AND t.training_rank <= 2
ORDER BY t.training_rank, f.exercise_order, f.set_number;
