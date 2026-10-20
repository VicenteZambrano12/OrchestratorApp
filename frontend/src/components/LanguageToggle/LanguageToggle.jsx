/**
 * @file Reusable locale selector backed by the shared i18next instance.
 * Language changes affect both translated UI and subsequent agent request payloads.
 * Storage failures are shown separately from the locale already applied in memory.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { setLanguage } from '../../i18n'
import { createLogger, errorType } from '../../lib/observability/logger'

const logger = createLogger('language')

/**
 * Renders English/Spanish controls using the current translation context.
 * Accepts no props; local error state records language-persistence failures.
 * @returns {import('react').ReactElement} Accessible locale buttons and optional alert.
 */
export default function LanguageToggle() {
  const { t, i18n } = useTranslation()
  const [error, setError] = useState('')

  /**
   * Applies and persists a supported locale through the shared i18n utility.
   * @param {'en'|'es'} language - Locale selected by the user.
   * @returns {Promise<void>} Settles after persistence or visible error reporting.
   */
  async function changeLanguage(language) {
    // 1. Delegate locale validation, activation, and persistence to the i18n module.
    try {
      await setLanguage(language)
      setError('')
    } catch (storageError) {
      // 2. Keep the active locale while exposing a failed persistence attempt.
      logger.error('language.save_failed', { error_type: errorType(storageError) })
      setError('Your language changed, but could not be saved on this device.')
    }
  }

  return <div className="language-controls">
    <div className="language-toggle" role="group" aria-label={t('Language')}>
      {['en', 'es'].map((language) => <button key={language} type="button" lang={language}
        aria-label={language === 'en' ? 'English' : 'Español'}
        aria-pressed={i18n.resolvedLanguage === language}
        onClick={() => changeLanguage(language)}>{language.toUpperCase()}</button>)}
    </div>
    {error && <span role="alert" className="error-message">{t(error)}</span>}
  </div>
}
