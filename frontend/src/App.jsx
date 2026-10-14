import { useEffect, useState } from 'react'
import AppSkeleton from './components/AppSkeleton/AppSkeleton'
import MainView from './pages/MainView/MainView'
import FailingView from './pages/FailingView/FailingView'
import { checkHealth } from './hooks/health/health'
import { useSession } from './hooks/session/session'
import { useTranslation } from 'react-i18next'

function App() {
  const { t } = useTranslation()
  const session = useSession()
  const [status, setStatus] = useState('checking')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    checkHealth(controller.signal)
      .then(() => setStatus('ready'))
      .catch(() => { if (!controller.signal.aborted) setStatus('failed') })
    return () => controller.abort()
  }, [attempt])

  if (status === 'failed') return <FailingView onRetry={() => { setStatus('checking'); setAttempt((n) => n + 1) }} />
  if (session.error) return <main className="help-modal">
    <p role="alert">{t('Could not initialize user session: {{message}}', { message: t(session.error) })}</p>
    <button className="primary-button" onClick={session.retry}>{t('Retry')}</button>
  </main>
  if (status === 'checking' || !session.user) return <AppSkeleton />
  return <MainView key={session.user.id} user={session.user} onSwitchUser={session.switchUser} />
}

export default App
