/**
 * @file Illustrative workout-history fixtures for the offline demo reply path.
 * Synthetic dates are relative to today; these rows never represent persisted
 * user workouts and explanations explicitly label them as demo data.
 */
const PUSH = [
  ['Barbell Bench Press', 'chest', [[8, 70], [8, 70], [6, 75], [6, 75]]],
  ['Seated Dumbbell Shoulder Press', 'shoulders', [[10, 22], [10, 22], [8, 24]]],
  ['Incline Dumbbell Press', 'chest', [[10, 26], [10, 26], [9, 26]]],
  ['Cable Lateral Raise', 'shoulders', [[15, 8], [14, 8], [12, 8]]],
  ['Triceps Pushdown', 'triceps', [[12, 30], [12, 30], [10, 32]]],
  ['Dips', 'triceps', [[12, 0], [10, 0], [9, 0]]],
]
const PULL = [
  ['Pull-Up', 'back', [[10, 0], [9, 0], [8, 0]]],
  ['Barbell Row', 'back', [[8, 65], [8, 65], [8, 65]]],
  ['Lat Pulldown', 'back', [[12, 55], [10, 60], [10, 60]]],
  ['Barbell Curl', 'biceps', [[10, 30], [10, 30], [8, 30]]],
  ['Hammer Curl', 'forearms', [[12, 14], [12, 14]]],
]
const LEGS = [
  ['Barbell Back Squat', 'quads', [[6, 100], [6, 100], [5, 105], [5, 105]]],
  ['Romanian Deadlift', 'hamstrings', [[8, 90], [8, 90], [8, 90]]],
  ['Hip Thrust', 'glutes', [[10, 110], [10, 110], [10, 110]]],
  ['Standing Calf Raise', 'calves', [[15, 60], [15, 60], [12, 60]]],
  ['Plank', 'core', [[1, 0], [1, 0]]],
]

/**
 * Creates a local calendar date for relative demo history.
 * @param {number} days - Days before today.
 * @returns {string} YYYY-MM-DD date without timezone conversion.
 */
function isoDaysAgo(days) {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

/**
 * Expands compact exercise tuples into illustrative backend-style set rows.
 * @param {number} trainingId - Synthetic session identifier.
 * @param {number} daysAgo - Relative session date.
 * @param {string} dayName - Split label.
 * @param {Array<[string, string, Array<[number, number]>]>} exercises - Name/muscle/reps-load tuples.
 * @param {object} [options={}] - Fixture adjustments.
 * @param {number} [options.bump=0] - Synthetic progression adjustment.
 * @param {object} [options.extra={}] - Additional route-specific scalar fields.
 * @returns {import('./reportData').ReportRow[]} Expanded set rows.
 */
function session(trainingId, daysAgo, dayName, exercises, { bump = 0, extra = {} } = {}) {
  return exercises.flatMap(([name, muscle, sets], exerciseIndex) => sets.map(([reps, weight], setIndex) => ({
    training_id: trainingId,
    training_date: isoDaysAgo(daysAgo),
    training_day: dayName,
    exercise_order: exerciseIndex + 1,
    exercise_name: name,
    primary_muscle: muscle,
    set_number: setIndex + 1,
    reps: Math.max(1, reps + (weight === 0 ? bump : 0)),
    weight: weight === 0 ? 0 : Math.max(0, weight + bump * (exerciseIndex % 2 ? -1 : 2.5)),
    weight_unit: 'kg',
    duration_seconds: null,
    distance_meters: null,
    rpe: Math.min(10, 7 + setIndex * 0.5),
    ...extra,
  })))
}

/**
 * Selects a comparison, weekly, or last-session demonstration from prompt keywords.
 * @param {string} query - Demo prompt, not sent to the backend.
 * @returns {import('./reportData').PastRoutinesAnalysis} Labeled illustrative report.
 */
export function demoPastRoutinesAnalysis(query) {
  if (/compar|last two|vs|versus/i.test(query)) {
    return {
      route: 'compare_last_two_workouts',
      day_type: 'push',
      data: [
        ...session(12, 1, 'Push Day A (Chest/Triceps/Delts)', PUSH, { bump: 1, extra: { training_rank: 1 } }),
        ...session(9, 8, 'Push Day A (Chest/Triceps/Delts)', PUSH, { extra: { training_rank: 2 } }),
      ],
      llm_explain: '### Push day: latest vs previous\n\nThis is **demo data**. Your bench press moved up **2.5 kg** at the same reps and dips gained a rep per set — great progress on pressing strength. Shoulder press and triceps pushdown dropped slightly; keep the load and aim to win back those reps next session.',
    }
  }
  if (/week|semana|month|progress/i.test(query)) {
    return {
      route: 'weekly_performance',
      day_type: null,
      data: [
        ...session(10, 5, 'Push Day A (Chest/Triceps/Delts)', PUSH),
        ...session(11, 3, 'Pull Day A (Back/Biceps)', PULL),
        ...session(12, 1, 'Leg Day & Core', LEGS),
      ],
      llm_explain: '### Your week at a glance\n\nThis is **demo data**. You trained **3 days** and hit every major muscle group. Back and quads carried the most work, while forearms and core were the lightest — consider one extra set for each. Your heaviest lift was the **hip thrust at 110 kg**.',
    }
  }
  return {
    route: 'past_day_exercise',
    day_type: 'pull',
    data: session(11, 3, 'Pull Day A (Back/Biceps)', PULL),
    llm_explain: '### Your last pull day\n\nThis is **demo data**. You completed **5 exercises** with solid consistency. Lat pulldown went up to 60 kg after the first set, and pull-ups held between 8 and 10 reps. Next time, try adding a rep on the last pull-up set.',
  }
}
