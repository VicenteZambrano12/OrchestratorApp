import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { workoutSetsError } from '../../features/RoutineView/workout-session/workoutSets'

export default function WorkoutFinishDialog({ sets, onConfirm, onClose }) {
  const { t } = useTranslation()
  const dialogRef = useRef(null)
  const inFlight = useRef(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const dialog = dialogRef.current
    dialog.showModal()
    return () => dialog.close()
  }, [])

  async function confirm(event) {
    event.preventDefault()
    if (inFlight.current) return
    setError('')
    const validation = workoutSetsError(sets)
    if (validation) {
      setError(t(validation))
      return
    }
    inFlight.current = true
    setSaving(true)
    try {
      await onConfirm(sets.map((set) => ({
        exercise_id: set.exercise_id, reps: Number(set.reps), weight: set.weight.trim() === '' ? null : Number(set.weight),
      })))
    } catch (saveError) {
      setError(t('Could not save workout: {{message}}', { message: t(saveError.message) }))
    } finally {
      inFlight.current = false
      setSaving(false)
    }
  }

  return <dialog ref={dialogRef} className="exercise-dialog workout-finish-dialog" aria-labelledby="workout-finish-title" aria-describedby="workout-finish-disclaimer"
    onCancel={(event) => { event.preventDefault(); if (!saving) onClose() }}
    onClick={(event) => { if (!saving && event.target === event.currentTarget) onClose() }}>
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
  </dialog>
}
