import { RotateCcw, ServerCrash } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import LanguageToggle from '../../components/LanguageToggle/LanguageToggle'

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
