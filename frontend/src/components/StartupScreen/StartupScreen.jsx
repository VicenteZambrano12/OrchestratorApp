import { useEffect, useId, useRef } from 'react'
import { motion, useIsPresent, useReducedMotion } from 'framer-motion'
import { Activity, RotateCcw, ServerCrash, UserRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import LanguageToggle from '../LanguageToggle/LanguageToggle'
import './StartupScreen.css'

/**
 * Full-page startup state, not a modal: recovery remains reachable at any zoom.
 * @param {{kind?: 'loading'|'backend'|'session', message?: string, onRetry?: () => void}} props
 */
export default function StartupScreen({ kind = 'loading', message, onRetry }) {
  const { t } = useTranslation()
  const headingId = useId()
  const headingRef = useRef(null)
  const isPresent = useIsPresent()
  const reducedMotion = useReducedMotion() !== false
  const loading = kind === 'loading'
  const Icon = loading ? Activity : kind === 'backend' ? ServerCrash : UserRound
  const title = loading ? t('Loading your workspace')
    : kind === 'backend' ? t('Backend unavailable') : t('Session unavailable')
  const description = loading ? t('Checking the server and preparing your session.')
    : kind === 'backend'
      ? t('We couldn’t reach the server. Make sure the backend is running and try again.')
      : t('Could not initialize user session: {{message}}', { message })

  useEffect(() => {
    if (!loading) headingRef.current?.focus({ preventScroll: true })
  }, [loading])

  return (
    <motion.main
      className="startup-screen grid min-w-0"
      aria-labelledby={headingId}
      inert={!isPresent}
      initial={reducedMotion ? false : { opacity: 0, y: 'var(--startup-offset)' }}
      animate={{ opacity: 1, y: 0 }}
      exit={reducedMotion ? { opacity: 1 } : { opacity: 0, y: 'var(--startup-offset)' }}
      transition={{ duration: reducedMotion ? 0 : 0.18, ease: 'easeOut' }}
    >
      <section className="startup-panel grid min-w-0 gap-6">
        <header className="flex min-w-0 flex-wrap items-center justify-between gap-4">
          <span className="startup-icon" aria-hidden="true"><Icon size={24} /></span>
          <LanguageToggle />
        </header>

        <div className="grid min-w-0 gap-4">
          <h1 ref={headingRef} id={headingId} tabIndex={-1}>{title}</h1>
          <p role={loading ? 'status' : 'alert'} aria-atomic="true">{description}</p>
        </div>

        {loading ? (
          <div className="startup-preview grid min-w-0 gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"
            aria-hidden="true">
            <div className="grid content-start gap-4">
              <div className="startup-placeholder startup-placeholder-heading" />
              <div className="startup-placeholder startup-placeholder-row" />
              <div className="startup-placeholder startup-placeholder-row" />
            </div>
            <div className="startup-placeholder startup-placeholder-content" />
          </div>
        ) : (
          <button type="button" className="startup-retry" onClick={onRetry}>
            <RotateCcw size={20} aria-hidden="true" />
            <span>{t('Retry')}</span>
          </button>
        )}
      </section>
    </motion.main>
  )
}
