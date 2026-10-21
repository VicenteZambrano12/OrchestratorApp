/**
 * @file Agent conversation acknowledgement for an already-persisted routine.
 * This component displays confirmed save feedback; it does not initiate a write.
 */
import { CheckCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import './SavedRoutine.css'

/**
 * Displays a saved plan's name and backend/API-normalized confirmation text.
 * @param {object} props - Confirmation properties.
 * @param {{name: string, id?: number}} props.routine - Confirmed saved-routine descriptor.
 * @param {string} props.message - Save confirmation text.
 * @returns {import('react').ReactElement} Localized save acknowledgement.
 */
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
