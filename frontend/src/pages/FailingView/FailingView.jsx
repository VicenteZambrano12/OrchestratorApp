/**
 * @file Backend-unavailable page shared by startup health and runtime outage recovery.
 * Retry semantics belong to the caller: startup repeats health checks, while the
 * workspace reveals its preserved shell so the user can retry the failed action.
 */
import { RotateCcw, ServerCrash } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import LanguageToggle from '../../components/LanguageToggle/LanguageToggle'

/**
 * Presents a localized backend failure alert with language controls and recovery.
 * @param {object} props - Recovery view properties.
 * @param {() => void} props.onRetry - Caller-specific recovery action.
 * @returns {import('react').ReactElement} Full-page backend-unavailable message.
 */
function FailingView({ onRetry }) {
  const { t } = useTranslation()
  return (
    <main className="failing-view">
      <section className="failing-card" role="alert">
        <ServerCrash size={32} aria-hidden="true" />
        <LanguageToggle />
        <h1>{t('Backend unavailable')}</h1>
        <p>{t('We couldn’t reach the server. Make sure the backend is running and try again.')}</p>
        <button type="button" className="retry-button" onClick={onRetry}>
          <RotateCcw size={16} aria-hidden="true" /> {t('Retry')}
        </button>
      </section>
    </main>
  )
}

export default FailingView
