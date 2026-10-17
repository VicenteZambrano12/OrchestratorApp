import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

export default function RoutineUpdateDialog({ onConfirm, onClose }) {
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
    inFlight.current = true
    setSaving(true)
    setError('')
    try {
      await onConfirm()
    } catch (saveError) {
      setError(t('Could not save routine: {{message}}', { message: t(saveError.message) }))
    } finally {
      inFlight.current = false
      setSaving(false)
    }
  }

  return <dialog ref={dialogRef} className="exercise-dialog" aria-labelledby="routine-update-title" aria-describedby="routine-update-disclaimer"
    onCancel={(event) => { event.preventDefault(); if (!saving) onClose() }}
    onClick={(event) => { if (!saving && event.target === event.currentTarget) onClose() }}>
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
  </dialog>
}
