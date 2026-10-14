import { useEffect, useState } from 'react'
import { activateUser, listUsers } from './users'

export function useSession() {
  const [user, setUser] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    async function initialize() {
      try {
        const users = await listUsers(controller.signal)
        if (!users.length) throw new Error('No users are available.')
        const selected = await activateUser(users[0], controller.signal)
        if (!controller.signal.aborted) setUser(selected)
      } catch (error) {
        if (!controller.signal.aborted) setError(error.message)
      }
    }
    initialize()
    return () => controller.abort()
  }, [attempt])

  async function switchUser(next, signal) {
    const selected = await activateUser(next, signal)
    if (!signal?.aborted) setUser(selected)
  }

  return { user, error, switchUser, retry: () => { setError(''); setAttempt((n) => n + 1) } }
}
