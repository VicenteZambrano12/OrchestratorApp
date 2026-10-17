import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { isValidExerciseField } from '../../features/RoutineView/workout-editing/workoutEditing'

export default function ExerciseValueInput({ exercise, field, onChange, weightUnit = 'kg' }) {
  const { t } = useTranslation()
  const [focused, setFocused] = useState(false)
  const value = exercise[field]
  const isWeight = field === 'weight'

  return <input className="exercise-input" aria-label={`${t(exercise.name)} ${t(field)}`}
    aria-invalid={!isValidExerciseField(field, value)} type={field === 'reps' ? 'text' : 'number'}
    min={field === 'sets' ? 1 : 0} max={field === 'sets' ? 20 : undefined} step={isWeight ? 'any' : 1}
    value={isWeight && (value === 0 || (!focused && Number(value) === 0)) ? '' : value} placeholder={isWeight ? `-- ${weightUnit}` : undefined}
    onFocus={(event) => { setFocused(true); event.target.select() }}
    onChange={(event) => onChange(event.target.value)}
    onBlur={() => {
      setFocused(false)
      if (isWeight && value === '') onChange(0)
      else if (field !== 'reps' && isValidExerciseField(field, value)) onChange(Number(value))
    }} />
}
