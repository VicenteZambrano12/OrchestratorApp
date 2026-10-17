export function createWorkoutSets(exercises) {
  return exercises.flatMap((exercise, exerciseIndex) =>
    Array.from({ length: Number(exercise.sets) }, (_, index) => ({
      exerciseIndex, exercise_id: exercise.exerciseId, name: exercise.name,
      setNumber: index + 1, reps: '', weight: String(exercise.weight),
    })))
}

export function filledWorkoutSets(sets) {
  return sets.filter((set) => set.reps.trim() !== '')
}

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
