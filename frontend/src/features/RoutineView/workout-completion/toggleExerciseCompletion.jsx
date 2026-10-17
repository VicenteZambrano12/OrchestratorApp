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
