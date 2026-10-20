/**
 * @file Controlled target input preserving draft text until blur normalization.
 * Focus state distinguishes an actively typed zero from the empty weight placeholder.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { isValidExerciseField } from '../../features/RoutineView/workout-editing/workoutEditing'

/**
 * Renders one validated target field without persisting the surrounding routine.
 * @param {object} props - Input properties.
 * @param {import('../../features/RoutineMaker/routine-data/routineData').WorkoutExercise} props.exercise - Current exercise.
 * @param {'sets'|'reps'|'weight'} props.field - Target to edit.
 * @param {(value: number|string) => void} props.onChange - Receives draft text or normalized number.
 * @param {string} [props.weightUnit='kg'] - Placeholder unit, without conversion.
 * @returns {import('react').ReactElement} Accessible controlled target input.
 */
export default function ExerciseValueInput({ exercise, field, onChange, weightUnit = 'kg' }) {
  const { t } = useTranslation()
  const [focused, setFocused] = useState(false)
  const value = exercise[field]
  const isWeight = field === 'weight'

  return <input className="exercise-input" aria-label={`${t(exercise.name)} ${t(field)}`}
    aria-invalid={!isValidExerciseField(field, value)} type={field === 'reps' ? 'text' : 'number'}
    min={field === 'sets' ? 1 : 0} max={field === 'sets' ? 20 : undefined} step={isWeight ? 'any' : 1}
    value={isWeight && (value === 0 || (!focused && Number(value) === 0)) ? '' : value} placeholder={isWeight ? `-- ${weightUnit}` : undefined}
    onFocus={(event) => {
      // 1. Preserve actively entered zeros and select the target for quick replacement.
      setFocused(true); event.target.select()
    }}
    onChange={(event) => onChange(event.target.value)}
    onBlur={() => {
      // 1. Leave text-entry mode before normalizing numeric target fields.
      setFocused(false)
      // 2. Treat empty planned load as zero; preserve invalid drafts for correction.
      if (isWeight && value === '') onChange(0)
      else if (field !== 'reps' && isValidExerciseField(field, value)) onChange(Number(value))
    }} />
}
