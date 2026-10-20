/**
 * @file Theme state provider bridging pre-render DOM preferences, system media
 * changes, and cross-tab storage events. Persistence errors remain visible without
 * rolling back the theme already applied to the current document.
 */
import { useEffect, useLayoutEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ThemeContext } from '../../hooks/theme/ThemeContext'
import { applyTheme, isThemePreference, themeStorageKey } from '../../utils/styles'
import { createLogger, errorType } from '../../lib/observability/logger'

const logger = createLogger('theme')

/**
 * Provides theme selection and the resolved light/dark appearance to descendants.
 * Initial state comes from the document's bootstrap attributes, avoiding a flash
 * between the pre-render theme and React's first paint.
 * @param {object} props - Provider properties.
 * @param {import('react').ReactNode} props.children - The application subtree.
 * @returns {import('react').ReactElement} Context provider and dismissible storage alert.
 */
export function ThemeProvider({ children }) {
  const { t } = useTranslation()
  const [preference, setPreference] = useState(() => document.documentElement.dataset.themePreference || 'system')
  const [resolvedTheme, setResolvedTheme] = useState(() => document.documentElement.classList.contains('dark') ? 'dark' : 'light')
  const [error, setError] = useState(() => document.documentElement.dataset.themeError || '')

  /**
   * Applies a validated preference to the DOM and in-memory context.
   * @param {'light'|'dark'|'system'} next - Requested preference.
   * @returns {void}
   * @throws {Error} If the preference is unsupported.
   */
  function updateTheme(next) {
    // 1. Reject unsupported preferences before changing document appearance.
    if (!isThemePreference(next)) throw new Error(`Invalid theme preference: ${next}`)
    // 2. Keep resolved appearance and user preference distinct for system mode.
    setResolvedTheme(applyTheme(next))
    setPreference(next)
  }

  /**
   * Changes appearance immediately and reports device-persistence failures.
   * @param {'light'|'dark'|'system'} next - Requested preference.
   * @returns {void}
   */
  function setTheme(next) {
    // 1. Apply the preference even if device storage is unavailable.
    updateTheme(next)
    // 2. Persist for reloads; retain the applied theme and show errors on failure.
    try {
      localStorage.setItem(themeStorageKey, next)
      setError('')
    } catch (storageError) {
      logger.error('theme.save_failed', { error_type: errorType(storageError) })
      setError('Your theme changed, but could not be saved on this device.')
    }
  }

  useLayoutEffect(() => {
    // 1. Subscribe before paint so system-mode changes update the current frame.
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    /** @returns {void} Updates appearance only while system mode is selected. */
    function syncSystemTheme() {
      if (preference === 'system') setResolvedTheme(applyTheme('system'))
    }
    // 2. Synchronize immediately and release the listener when preference changes.
    media.addEventListener('change', syncSystemTheme)
    syncSystemTheme()
    return () => media.removeEventListener('change', syncSystemTheme)
  }, [preference])

  useEffect(() => {
    // 1. Handle only theme changes from this origin's local storage.
    /**
     * Mirrors a validated cross-tab preference without writing it back to storage.
     * @param {StorageEvent} event - Browser storage notification.
     * @returns {void}
     */
    function syncStorage(event) {
      if (event.storageArea !== localStorage || (event.key !== themeStorageKey && event.key !== null)) return
      // 2. Treat removal as system mode; expose malformed stored values to the UI.
      const next = event.newValue ?? 'system'
      if (!isThemePreference(next)) {
        logger.warn('theme.invalid_preference')
        setError('A theme preference from another tab was not recognized.')
        return
      }
      // 3. Apply the other tab's preference without creating a storage feedback loop.
      updateTheme(next)
      setError('')
    }
    // 4. Keep one cross-tab listener for the provider's lifetime.
    window.addEventListener('storage', syncStorage)
    return () => window.removeEventListener('storage', syncStorage)
  }, [])

  return <ThemeContext.Provider value={{ theme: preference, resolvedTheme, setTheme }}>
    {children}
    {error && <div className="theme-error error-message" role="alert">
      <span>{t(error)}</span><button type="button" className="text-button" onClick={() => setError('')}>{t('Dismiss')}</button>
    </div>}
  </ThemeContext.Provider>
}
