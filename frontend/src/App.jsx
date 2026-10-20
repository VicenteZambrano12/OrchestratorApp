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
import { AnimatePresence } from 'framer-motion'
import AppSkeleton from './components/AppSkeleton/AppSkeleton'
import MainView from './pages/MainView/MainView'
import FailingView from './pages/FailingView/FailingView'
import { checkHealth } from './hooks/health/health'
import { useSession } from './hooks/session/session'
import { useTranslation } from 'react-i18next'
import { createLogger, errorType } from './lib/observability/logger'
import StartupScreen from './components/StartupScreen/StartupScreen'

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
    const controller = new AbortController()
    checkHealth(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) setStatus('ready')
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          logger.error('app.health_failed', { error_type: errorType(error) })
          setStatus('failed')
        }
      })
    return () => controller.abort()
  }, [attempt])

  function retryHealth() {
    setStatus('checking')
    setAttempt((n) => n + 1)
  }

  let view
  // Backend failure takes precedence; each recovery action retries only its owner.
  if (status === 'failed') {
    view = <FailingView key="backend" onRetry={retryHealth} />
  } else if (session.error) {
    view = <StartupScreen key="session" kind="session" message={t(session.error)} onRetry={session.retry} />
  } else if (status === 'checking' || !session.user) {
    view = <AppSkeleton key="loading" />
  } else {
    // Preserve the user identity boundary for all user-scoped workspace state.
    view = <MainView key={session.user.id} user={session.user} onSwitchUser={session.switchUser} />
  }

  return <AnimatePresence mode="wait" initial={false}>{view}</AnimatePresence>
}

export default App
