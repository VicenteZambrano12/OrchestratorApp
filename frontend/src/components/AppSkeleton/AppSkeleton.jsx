import { useTranslation } from 'react-i18next'

export default function AppSkeleton() {
  const { t } = useTranslation()
  return <div className="app-shell skeleton-shell" role="status" aria-busy="true" aria-label={t('Loading your workspace')}>
    <aside className="sidebar">
      <div className="skeleton skeleton-line skeleton-w-40" />
      <div className="skeleton skeleton-block" />
      <div className="skeleton skeleton-block" />
    </aside>
    <div className="main-shell">
      <div className="skeleton skeleton-line skeleton-w-30" />
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-line skeleton-w-60" />
      <div className="skeleton skeleton-card" />
    </div>
    <span className="sr-only">{t('Loading…')}</span>
  </div>
}
