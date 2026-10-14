import { useEffect, useState } from 'react'
import MainView from './pages/MainView/MainView'
import FailingView from './pages/FailingView/FailingView'
import { checkHealth } from './hooks/health/health'
import { useSession } from './hooks/session/session'

function App() {
  useSession()
  const [status, setStatus] = useState('checking')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    checkHealth(controller.signal)
      .then(() => setStatus('ready'))
      .catch(() => { if (!controller.signal.aborted) setStatus('failed') })
    return () => controller.abort()
  }, [attempt])

  if (status === 'checking') return null
  if (status === 'failed') return <FailingView onRetry={() => { setStatus('checking'); setAttempt((n) => n + 1) }} />
  return <MainView />
}

export default App
