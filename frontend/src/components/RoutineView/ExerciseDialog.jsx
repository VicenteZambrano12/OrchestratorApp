/**
 * @file Native modal for adding or swapping exercises in a controlled routine draft.
 * Suggestions preserve catalog identity; custom names remain local and cannot be
 * persisted as catalog-backed routine targets by the complete-plan serializer.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

/**
 * Captures an exercise name and explicit rest duration using native form validation.
 * @param {object} props - Dialog properties.
 * @param {import('../../features/RoutineMaker/routine-data/routineData').WorkoutExercise|null} props.exercise - Swap target, or null to add.
 * @param {import('../../features/RoutineMaker/routine-data/routineData').WorkoutExercise[]} props.suggestions - Available catalog/name matches.
 * @param {(selection: {name: string, exerciseId: number|null, rest: string}) => void} props.onConfirm - Publishes selection.
 * @param {() => void} props.onClose - Parent-owned dismissal and focus restoration.
 * @returns {import('react').ReactElement} Localized add/swap modal.
 */
export default function ExerciseDialog({ exercise, suggestions, onConfirm, onClose }) {
  const { t } = useTranslation()
  const dialogRef = useRef(null)
  const swapping = Boolean(exercise)

  useEffect(() => {
    // 1. Enter the native modal focus boundary after the element mounts.
    const dialog = dialogRef.current
    dialog.showModal()
    // 2. Release modal state when the parent removes the dialog.
    return () => dialog.close()
  }, [])

  /**
   * Resolves translated suggestions to stable identities before publishing selection.
   * @param {import('react').SubmitEvent<HTMLFormElement>} event - Form submission.
   * @returns {void}
   */
  function submit(event) {
    // 1. Keep submission local and surface blank-name errors through native validity.
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const name = String(data.get('name')).trim()
    if (!name) {
      event.currentTarget.elements.name.setCustomValidity(t('Enter an exercise name.'))
      event.currentTarget.elements.name.reportValidity()
      return
    }
    // 2. Preserve catalog identity where possible; custom names use a null ID.
    const selected = suggestions.find((item) => item.name === name || t(item.name) === name)
    onConfirm({ name: selected?.name ?? name, exerciseId: selected?.exerciseId ?? null, rest: `${Number(data.get('rest'))}s` })
  }

  return <dialog ref={dialogRef} className="exercise-dialog" aria-labelledby="exercise-dialog-title"
    onCancel={(event) => { event.preventDefault(); onClose() }}
    onClick={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <form onSubmit={submit}>
      <div className="exercise-dialog-heading"><h3 id="exercise-dialog-title">{t(swapping ? 'Swap exercise' : 'Add exercise')}</h3><button type="button" className="icon-button" aria-label={t('Close')} onClick={onClose}><X size={18} /></button></div>
      <label>{t('Exercise name')}<input name="name" required autoFocus maxLength={120} list="exercise-suggestions"
        placeholder={swapping ? t(exercise.name) : t('Exercise name')} onChange={(event) => event.target.setCustomValidity('')} /></label>
      <datalist id="exercise-suggestions">{suggestions.map((item) => <option key={item.name} value={t(item.name)} />)}</datalist>
      <p>{t('Choose a suggestion or enter your own exercise.')}</p>
      <label>{t('Rest (seconds)')}<input name="rest" type="number" min="0" max="900" step="1" required defaultValue="90" /></label>
      <div className="button-group"><button type="button" className="secondary-button" onClick={onClose}>{t('Cancel')}</button><button className="primary-button" type="submit">{t(swapping ? 'Swap exercise' : 'Add exercise')}</button></div>
    </form>
  </dialog>
}
