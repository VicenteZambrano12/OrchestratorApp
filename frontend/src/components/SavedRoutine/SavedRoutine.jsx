import { CheckCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import './SavedRoutine.css'

export default function SavedRoutine({ routine, message }) {
  const { t } = useTranslation()
  return <section className="saved-routine" aria-label={t('Routine saved')}>
    <header>
      <CheckCheck size={22} aria-hidden="true" />
      <div><h3>{t('Routine saved')}</h3><p>{routine.name}</p></div>
    </header>
    <p>{message}</p>
  </section>
}
