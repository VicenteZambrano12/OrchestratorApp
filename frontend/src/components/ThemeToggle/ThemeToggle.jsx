import { Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useTheme } from '../../hooks/theme/useTheme'

export default function ThemeToggle() {
  const { t } = useTranslation()
  const { theme, resolvedTheme, setTheme } = useTheme()
  return <div className="theme-controls">
    <button type="button"
      className="theme-toggle transition-transform duration-200 active:scale-95 focus-visible:ring-2 focus-visible:ring-emerald-600"
      aria-label={t('Toggle theme')} aria-pressed={resolvedTheme === 'dark'}
      title={t(resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode')}
      onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}>
      <Sun className="theme-sun" size={18} aria-hidden="true" />
      <Moon className="theme-moon" size={18} aria-hidden="true" />
    </button>
    <select className="theme-preference" aria-label={t('Theme preference')} value={theme} onChange={(event) => setTheme(event.target.value)}>
      <option value="light">{t('Light')}</option>
      <option value="dark">{t('Dark')}</option>
      <option value="system">{t('System')}</option>
    </select>
  </div>
}
