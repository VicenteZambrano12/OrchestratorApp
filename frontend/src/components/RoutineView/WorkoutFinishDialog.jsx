/**
 * @file Performed-workout save confirmation and API payload normalization.
 * Validates filled sets from completed exercises and keeps the workout active when
 * saving fails; planned targets are not used as substitutes for actual repetitions.
 */
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { workoutSetsError } from '../../features/RoutineView/workout-session/workoutSets'
import AdaptiveDialog from '../AdaptiveDialog/AdaptiveDialog'

/**
 * Confirms actual-set persistence with native modal focus and duplicate-write guards.
 * @param {object} props - Dialog properties.
 * @param {import('../../features/RoutineView/workout-session/workoutSets').WorkoutSet[]} props.sets - Filled, completed-exercise sets.
 * @param {(sets: Array<{exercise_id: number, reps: number, weight: number|null}>) => Promise<void>} props.onConfirm - Persists and ends session on success.
 * @param {() => void} props.onClose - Resumes the active workout.
 * @returns {import('react').ReactElement} Save confirmation with validation/API alerts.
 */
export default function WorkoutFinishDialog({ sets, onConfirm, onClose }) {
  const { t } = useTranslation()
  const inFlight = useRef(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  /**
   * Validates actual sets, normalizes numbers, and awaits parent-owned persistence.
   * @param {import('react').SubmitEvent<HTMLFormElement>} event - Form submission.
   * @returns {Promise<void>} Settles with visible validation/save feedback.
   */
  async function confirm(event) {
    // 1. Reject duplicate submissions and validate before acquiring the save lock.
    event.preventDefault()
    if (inFlight.current) return
    setError('')
    const validation = workoutSetsError(sets)
    if (validation) {
      setError(t(validation))
      return
    }
    // 2. Serialize actual numbers; blank load remains unknown (null), not zero.
    inFlight.current = true
    setSaving(true)
    try {
      await onConfirm(sets.map((set) => ({
        exercise_id: set.exercise_id, reps: Number(set.reps), weight: set.weight.trim() === '' ? null : Number(set.weight),
      })))
    } catch (saveError) {
      // 3. Preserve parent session/input state and show the backend failure for retry.
      setError(t('Could not save workout: {{message}}', { message: t(saveError.message) }))
    } finally {
      // 4. Release pending state regardless of persistence outcome.
      inFlight.current = false
      setSaving(false)
    }
  }

  return <AdaptiveDialog className="exercise-dialog workout-finish-dialog" aria-labelledby="workout-finish-title" aria-describedby="workout-finish-disclaimer"
    dismissible={!saving} onClose={onClose}>
    <form onSubmit={confirm} aria-busy={saving}>
      <h3 id="workout-finish-title">{t('Finish and save your workout?')}</h3>
      <p id="workout-finish-disclaimer">{t('Only filled sets from exercises marked Done will be saved. Sets with blank reps and empty exercises are skipped. Your workout will finish only after it is saved successfully.')}</p>
      {sets.length === 0 && <p role="alert">{t(workoutSetsError(sets))}</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
      <div className="button-group">
        <button type="button" className="secondary-button" autoFocus disabled={saving} onClick={onClose}>{t('Keep working out')}</button>
        <button type="submit" className="primary-button" disabled={saving || sets.length === 0}>{t(saving ? 'Saving workout…' : 'Yes, finish and save')}</button>
      </div>
    </form>
  </AdaptiveDialog>
}
