import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

export default function ExerciseDialog({ exercise, suggestions, onConfirm, onClose }) {
  const { t } = useTranslation()
  const dialogRef = useRef(null)
  const swapping = Boolean(exercise)

  useEffect(() => {
    const dialog = dialogRef.current
    dialog.showModal()
    return () => dialog.close()
  }, [])

  function submit(event) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const name = String(data.get('name')).trim()
    if (!name) {
      event.currentTarget.elements.name.setCustomValidity(t('Enter an exercise name.'))
      event.currentTarget.elements.name.reportValidity()
      return
    }
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
