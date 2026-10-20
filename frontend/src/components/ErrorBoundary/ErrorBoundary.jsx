/**
 * @file Last-resort React rendering boundary around the application providers.
 * Render failures are logged with sanitized error types and replaced by a reload
 * screen; asynchronous API and agent-pipeline errors are handled by their callers.
 */
import { Component } from 'react'
import { useTranslation } from 'react-i18next'
import { createLogger, errorType } from '../../lib/observability/logger'

const logger = createLogger('react')

/**
 * Offers full-page recovery when rendering can no longer continue.
 * Accepts no props; reads translations and warns that reloading can lose edits.
 * @returns {import('react').ReactElement} Localized fatal-error screen.
 */
function CrashFallback() {
  const { t } = useTranslation()
  return <main className="failing-view">
    <section className="failing-card" role="alert">
      <h1>{t('Something went wrong')}</h1>
      <p>{t('The app encountered an unexpected error. Reload to try again. Unsaved changes may be lost.')}</p>
      <button type="button" className="retry-button" onClick={() => window.location.reload()}>
        {t('Reload app')}
      </button>
    </section>
  </main>
}

/**
 * Keeps a failed descendant tree unmounted until the application is reloaded.
 * @extends {Component}
 * @property {{children: import('react').ReactNode}} props - Protected subtree.
 * @property {{failed: boolean}} state - Latched render-failure state.
 */
export default class ErrorBoundary extends Component {
  state = { failed: false }

  /** @returns {{failed: boolean}} State selecting the fatal-error fallback. */
  static getDerivedStateFromError() {
    return { failed: true }
  }

  /**
   * Reports a descendant rendering error without logging its potentially private text.
   * @param {unknown} error - Error captured by React.
   * @returns {void}
   */
  componentDidCatch(error) {
    logger.error('react.render_failed', { error_type: errorType(error) })
  }

  /** @returns {import('react').ReactNode} Protected children or the reload fallback. */
  render() {
    return this.state.failed ? <CrashFallback /> : this.props.children
  }
}
