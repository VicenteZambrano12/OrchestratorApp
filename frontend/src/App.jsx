/**
 * @file Application-level startup gate for the agent orchestration UI.
 *
 * Coordinates an abortable backend health check with independent user-session
 * initialization before mounting the interactive MainView. Startup failures use
 * separate backend and session recovery screens; pending prerequisites share
 * AppSkeleton so user-scoped features do not mount before a user is available.
 *
 * This module only checks backend readiness. MainView and its chat API utilities
 * own agent requests, asynchronous pipeline state, streamed NDJSON responses
 * (not SSE or WebSockets), and request-time failure presentation.
 */
import { useEffect, useState } from 'react'
import AppSkeleton from './components/AppSkeleton/AppSkeleton'
import MainView from './pages/MainView/MainView'
import FailingView from './pages/FailingView/FailingView'
import { checkHealth } from './hooks/health/health'
import { useSession } from './hooks/session/session'
import { useTranslation } from 'react-i18next'
import { createLogger, errorType } from './lib/observability/logger'

const logger = createLogger('app')

/**
 * Renders the application shell selected by backend readiness and session state.
 *
 * Accepts no props and declares no Props interface. Requires the configured
 * react-i18next instance for localized startup errors and retry controls.
 * The session hook supplies the active user, initialization error, retry action,
 * and user-switch action; its lifecycle is independent of the health check.
 *
 * Health checks run on mount and whenever the local retry counter changes.
 * Backend failure takes precedence over session failure, followed by the shared
 * loading state. A ready backend and an initialized user unlock MainView.
 *
 * @returns {import('react').ReactElement} Backend recovery, session recovery,
 * startup skeleton, or the user-scoped main application view.
 */
function App() {
  const { t } = useTranslation()
  const session = useSession()
  // Keep backend readiness separate from session initialization and chat failures.
  const [status, setStatus] = useState('checking')
  // A new counter value reruns the health effect even after repeated failures.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    // 1. Give each health-check attempt its own cancellation boundary.
    const controller = new AbortController()
    // 2. Check /health; the API utility enforces its timeout and healthy payload.
    checkHealth(controller.signal)
      .then(() => setStatus('ready'))
      .catch((error) => {
        // 3. Report genuine failures, not cancellation during effect cleanup.
        if (!controller.signal.aborted) {
          logger.error('app.health_failed', { error_type: errorType(error) })
          setStatus('failed')
        }
      })
    // 4. Cancel pending work on unmount or before the next retry starts.
    return () => controller.abort()
  }, [attempt])

  // Backend recovery wins when both independent startup prerequisites fail.
  if (status === 'failed') return <FailingView onRetry={() => {
    // 1. Restore the loading gate while backend readiness is re-evaluated.
    setStatus('checking')
    // 2. Schedule a fresh health check without restarting session initialization.
    setAttempt((n) => n + 1)
  }} />
  // Session retry belongs to useSession and does not repeat a successful health check.
  if (session.error) return <main className="help-modal">
    <p role="alert">{t('Could not initialize user session: {{message}}', { message: t(session.error) })}</p>
    <button className="primary-button" onClick={session.retry}>{t('Retry')}</button>
  </main>
  if (status === 'checking' || !session.user) return <AppSkeleton />
  // Remount on user identity changes to reset user-scoped conversation/workout state.
  return <MainView key={session.user.id} user={session.user} onSwitchUser={session.switchUser} />
}

export default App
