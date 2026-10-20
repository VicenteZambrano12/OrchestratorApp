/** @file Pure local completion update; does not record a workout or call the API. */

/**
 * Toggles one exercise's completion while preserving unaffected object identities.
 * @param {import('../../RoutineMaker/routine-data/routineData').WorkoutRoutine} routine - UI routine.
 * @param {number} dayIndex - Zero-based day.
 * @param {number} exerciseIndex - Zero-based exercise.
 * @returns {import('../../RoutineMaker/routine-data/routineData').WorkoutRoutine} Updated UI routine.
 */
export function toggleExerciseCompletion(routine, dayIndex, exerciseIndex) {
  return {
    ...routine,
    days: routine.days.map((day, i) => i === dayIndex
      ? {
        ...day,
        exercises: day.exercises.map((exercise, j) => j === exerciseIndex
          ? { ...exercise, completed: !exercise.completed }
          : exercise),
      }
      : day),
  }
}
