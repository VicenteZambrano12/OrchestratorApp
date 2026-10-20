/**
 * @file Performed-set construction and validation shared by workout UI and saving.
 * Reps remain strings while editing; blank reps mean skipped sets, while blank
 * weight means unknown load rather than zero.
 *
 * @typedef {object} WorkoutSet
 * @property {number} exerciseIndex - Zero-based index in the locked workout day.
 * @property {number|null|undefined} exercise_id - Catalog identifier required to save.
 * @property {string} name - Display name.
 * @property {number} setNumber - One-based set label.
 * @property {string} reps - Actual reps input, blank until performed.
 * @property {string} weight - Actual load input; blank is permitted.
 */

/**
 * Expands exercise targets into blank performed-set entries.
 * @param {import('../../RoutineMaker/routine-data/routineData').WorkoutExercise[]} exercises - Active day.
 * @returns {WorkoutSet[]} Ordered per-exercise set inputs.
 */
export function createWorkoutSets(exercises) {
  return exercises.flatMap((exercise, exerciseIndex) =>
    Array.from({ length: Number(exercise.sets) }, (_, index) => ({
      exerciseIndex, exercise_id: exercise.exerciseId, name: exercise.name,
      setNumber: index + 1, reps: '', weight: String(exercise.weight),
    })))
}

/**
 * Excludes skipped sets without coercing or validating entered repetitions.
 * @param {WorkoutSet[]} sets - Candidate performed sets.
 * @returns {WorkoutSet[]} Entries with nonblank reps.
 */
export function filledWorkoutSets(sets) {
  return sets.filter((set) => set.reps.trim() !== '')
}

/**
 * Validates selected sets before backend serialization.
 * @param {WorkoutSet[]} sets - Filled sets from exercises marked complete.
 * @returns {string} Translation key describing the first error, or an empty string.
 */
export function workoutSetsError(sets) {
  if (sets.length === 0) return 'Enter reps for at least one set in an exercise marked Done before finishing.'
  if (sets.some((set) => !Number.isSafeInteger(set.exercise_id) || set.exercise_id < 1)) {
    return 'Choose catalog exercises before saving a workout.'
  }
  if (sets.some((set) => !/^[1-9]\d*$/.test(set.reps) || !Number.isSafeInteger(Number(set.reps)) ||
    (set.weight.trim() !== '' && (!Number.isFinite(Number(set.weight)) || Number(set.weight) < 0)))) {
    return 'Filled sets need positive whole-number reps and a non-negative weight, or a blank weight.'
  }
  return ''
}
