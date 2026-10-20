/**
 * @file Pure immutable workout-editing helpers shared by inputs and the editor hook.
 * Input validation permits intermediate strings; API serialization applies the
 * stricter complete-plan contract separately.
 */

/**
 * Validates a target field using its editor-specific numeric/text constraints.
 * @param {'sets'|'reps'|'weight'} field - Target field.
 * @param {unknown} value - Current input value.
 * @returns {boolean} Whether the target is usable in the editor.
 */
export function isValidExerciseField(field, value) {
  if (field === 'reps') return typeof value === 'string' && value.trim().length > 0
  if ((typeof value !== 'number' && typeof value !== 'string') || String(value).trim() === '' || !Number.isFinite(Number(value))) return false
  return field === 'sets' ? Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= 20 : Number(value) >= 0
}

/**
 * Validates only editable set, repetition, and load targets.
 * @param {import('../../RoutineMaker/routine-data/routineData').WorkoutExercise} exercise - UI exercise.
 * @returns {boolean} Whether all editable targets are valid.
 */
export function isValidExercise(exercise) {
  return ['sets', 'reps', 'weight'].every((field) => isValidExerciseField(field, exercise[field]))
}

/**
 * Replaces one day's exercise array while preserving the remaining day objects.
 * @param {import('../../RoutineMaker/routine-data/routineData').WorkoutRoutine} routine - UI plan.
 * @param {number} dayIndex - Zero-based day to edit.
 * @param {(exercises: import('../../RoutineMaker/routine-data/routineData').WorkoutExercise[]) =>
 * import('../../RoutineMaker/routine-data/routineData').WorkoutExercise[]} update - Immutable array transform.
 * @returns {import('../../RoutineMaker/routine-data/routineData').WorkoutRoutine} Updated plan.
 */
export function updateDayExercises(routine, dayIndex, update) {
  return { ...routine, days: routine.days.map((day, index) => index === dayIndex
    ? { ...day, exercises: update(day.exercises) } : day) }
}

/**
 * Moves an exercise without mutating its array; invalid/no-op moves retain identity.
 * @param {import('../../RoutineMaker/routine-data/routineData').WorkoutExercise[]} exercises - Current ordering.
 * @param {number} from - Source index.
 * @param {number} to - Destination index.
 * @returns {import('../../RoutineMaker/routine-data/routineData').WorkoutExercise[]} Reordered or original array.
 */
export function moveExercise(exercises, from, to) {
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to < 0 ||
    from >= exercises.length || to >= exercises.length || from === to) return exercises
  const next = [...exercises]
  const [exercise] = next.splice(from, 1)
  next.splice(to, 0, exercise)
  return next
}
