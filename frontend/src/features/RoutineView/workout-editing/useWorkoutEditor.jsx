import { useState } from 'react'

export function useWorkoutEditor({ routine, dayIndex, setRoutine, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(null)
  const [validation, setValidation] = useState('')
  const displayed = editing ? draft : routine

  function startEditing() {
    setDraft(structuredClone(routine))
    setEditing(true)
  }

  function cancelEditing() {
    setEditing(false)
    setValidation('')
  }

  function changeExercise(index, field, value) {
    setDraft((current) => ({ ...current, days: current.days.map((item, i) => i === dayIndex
      ? { ...item, exercises: item.exercises.map((exercise, j) => j === index ? { ...exercise, [field]: value } : exercise) }
      : item) }))
  }

  function saveEdits() {
    if (draft.days.some((item) => item.exercises.some((exercise) => !Number.isInteger(Number(exercise.sets)) ||
      Number(exercise.sets) < 1 || Number(exercise.sets) > 10 || !exercise.reps.trim() ||
      exercise.weight === '' || !Number.isFinite(Number(exercise.weight)) || Number(exercise.weight) < 0))) {
      setValidation('Enter 1–10 sets, a rep target, and a weight of at least 0 kg.')
      return
    }
    const next = { ...draft, days: draft.days.map((item) => ({ ...item, exercises: item.exercises.map((exercise) => ({ ...exercise, sets: Number(exercise.sets), weight: Number(exercise.weight) })) })) }
    setRoutine(next)
    onSave(next)
    setEditing(false)
    setValidation('')
  }

  return { editing, displayed, validation, startEditing, cancelEditing, changeExercise, saveEdits }
}
