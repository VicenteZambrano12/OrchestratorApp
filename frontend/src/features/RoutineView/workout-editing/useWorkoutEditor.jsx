import { useState } from 'react'
import { isValidExercise, updateDayExercises, moveExercise } from './workoutEditing'

export function useWorkoutEditor({ routine, dayIndex, setRoutine, onSave }) {
  const [isEditing, setIsEditing] = useState(false)
  const validation = routine.days.some((day) => day.exercises.some((exercise) => !isValidExercise(exercise)))
    ? 'Enter 1–20 sets, a rep target, and a weight of at least 0 kg.' : ''

  function updateExercises(update) {
    const next = updateDayExercises(routine, dayIndex, update)
    setRoutine(next)
    if (next.days.every((day) => day.exercises.every(isValidExercise))) onSave?.(next)
  }

  function changeExercise(index, field, value) {
    updateExercises((exercises) => exercises.map((exercise, i) => i === index ? { ...exercise, [field]: value } : exercise))
  }

  function toggleEditing() {
    if (!isEditing || !validation) setIsEditing(!isEditing)
  }

  return {
    isEditing, validation, toggleEditing, changeExercise,
    addExercise: (exercise) => updateExercises((exercises) => [...exercises, exercise]),
    swapExercise: (index, replacement) => updateExercises((exercises) => exercises.map((exercise, i) => i === index
      ? { ...exercise, ...replacement, weight: 0, completed: false, muscle: '', notes: '' } : exercise)),
    removeExercise: (index) => updateExercises((exercises) => exercises.filter((_, i) => i !== index)),
    reorderExercise: (from, to) => updateExercises((exercises) => moveExercise(exercises, from, to)),
  }
}
