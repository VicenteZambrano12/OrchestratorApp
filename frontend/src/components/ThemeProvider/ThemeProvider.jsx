import { useEffect, useLayoutEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ThemeContext } from '../../hooks/theme/ThemeContext'
import { applyTheme, isThemePreference, themeStorageKey } from '../../utils/styles'

export function ThemeProvider({ children }) {
  const { t } = useTranslation()
  const [preference, setPreference] = useState(() => document.documentElement.dataset.themePreference || 'system')
  const [resolvedTheme, setResolvedTheme] = useState(() => document.documentElement.classList.contains('dark') ? 'dark' : 'light')
  const [error, setError] = useState(() => document.documentElement.dataset.themeError || '')

  function updateTheme(next) {
    if (!isThemePreference(next)) throw new Error(`Invalid theme preference: ${next}`)
    setResolvedTheme(applyTheme(next))
    setPreference(next)
  }

  function setTheme(next) {
    updateTheme(next)
    try {
      localStorage.setItem(themeStorageKey, next)
      setError('')
    } catch (storageError) {
      console.error('Could not save theme preference:', storageError)
      setError('Your theme changed, but could not be saved on this device.')
    }
  }

  useLayoutEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    function syncSystemTheme() {
      if (preference === 'system') setResolvedTheme(applyTheme('system'))
    }
    media.addEventListener('change', syncSystemTheme)
    syncSystemTheme()
    return () => media.removeEventListener('change', syncSystemTheme)
  }, [preference])

  useEffect(() => {
    function syncStorage(event) {
      if (event.storageArea !== localStorage || (event.key !== themeStorageKey && event.key !== null)) return
      const next = event.newValue ?? 'system'
      if (!isThemePreference(next)) {
        console.warn('Unrecognized form-theme preference:', next)
        setError('A theme preference from another tab was not recognized.')
        return
      }
      updateTheme(next)
      setError('')
    }
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
