export function isValidExerciseField(field, value) {
  if (field === 'reps') return typeof value === 'string' && value.trim().length > 0
  if ((typeof value !== 'number' && typeof value !== 'string') || String(value).trim() === '' || !Number.isFinite(Number(value))) return false
  return field === 'sets' ? Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= 20 : Number(value) >= 0
}

export function isValidExercise(exercise) {
  return ['sets', 'reps', 'weight'].every((field) => isValidExerciseField(field, exercise[field]))
}

export function updateDayExercises(routine, dayIndex, update) {
  return { ...routine, days: routine.days.map((day, index) => index === dayIndex
    ? { ...day, exercises: update(day.exercises) } : day) }
}

export function moveExercise(exercises, from, to) {
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to < 0 ||
    from >= exercises.length || to >= exercises.length || from === to) return exercises
  const next = [...exercises]
  const [exercise] = next.splice(from, 1)
  next.splice(to, 0, exercise)
  return next
}
