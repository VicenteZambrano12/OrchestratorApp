/**
 * @file Confirmation boundary for versioned routine saves.
 * In-flight state prevents duplicate writes and dismissal; save rejection remains
 * visible in the dialog without discarding the parent-owned edited routine.
 */
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import AdaptiveDialog from '../AdaptiveDialog/AdaptiveDialog'

/**
 * Confirms a new active routine version, excluding actual workout weights/completion.
 * @param {object} props - Dialog properties.
 * @param {() => Promise<void>} props.onConfirm - Parent-owned save action; closes on success.
 * @param {() => void} props.onClose - Returns to the draft without saving.
 * @returns {import('react').ReactElement} Modal with pending and recoverable error states.
 */
export default function RoutineUpdateDialog({ onConfirm, onClose }) {
  const { t } = useTranslation()
  const inFlight = useRef(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  /**
   * Serializes user confirmation and reports persistence errors in place.
   * @param {import('react').SubmitEvent<HTMLFormElement>} event - Form submission.
   * @returns {Promise<void>} Settles after save success or visible failure.
   */
  async function confirm(event) {
    // 1. Lock synchronously as well as visually to prevent same-frame duplicate writes.
    event.preventDefault()
    if (inFlight.current) return
    inFlight.current = true
    setSaving(true)
    setError('')
    // 2. Delegate persistence; parent changes edit mode only after success.
    try {
      await onConfirm()
    } catch (saveError) {
      setError(t('Could not save routine: {{message}}', { message: t(saveError.message) }))
    } finally {
      // 3. Release both guards so failed saves can be retried.
      inFlight.current = false
      setSaving(false)
    }
  }

  return <AdaptiveDialog className="exercise-dialog" aria-labelledby="routine-update-title" aria-describedby="routine-update-disclaimer"
    dismissible={!saving} onClose={onClose}>
    <form onSubmit={confirm} aria-busy={saving}>
      <h3 id="routine-update-title">{t('Update your routine?')}</h3>
      <p id="routine-update-disclaimer">{t('This will save your edits as a new active routine. Your previous routine will be kept as an inactive version.')}</p>
      <p>{t('Weights and exercise completion are not included in the routine. Finish a workout to save its completed sets.')}</p>
      {error && <p role="alert" className="error-message">{error}</p>}
      <div className="button-group">
        <button type="button" className="secondary-button" autoFocus disabled={saving} onClick={onClose}>{t('Keep editing')}</button>
        <button type="submit" className="primary-button" disabled={saving}>{t(saving ? 'Saving routine…' : 'Yes, update routine')}</button>
      </div>
    </form>
  </AdaptiveDialog>
}
