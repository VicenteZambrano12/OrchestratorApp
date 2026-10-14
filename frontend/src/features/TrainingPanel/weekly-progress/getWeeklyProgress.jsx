export function getWeeklyProgress(routine) {
  return {
    completed: routine.days.flatMap((day) => day.exercises).filter((exercise) => exercise.completed).length,
    weekDays: ['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((label, index) => ({
      label,
      isTrainingDay: [0, 2, 4].includes(index),
    })),
  }
}
