/**
 * @file Application session hook selecting the first backend profile and activating
 * its orchestrator conversation. Initialization is independent of App's health
 * check; all errors are surfaced for explicit retry instead of fabricating a user.
 */
import { useEffect, useState } from 'react'
import { activateUser, listUsers } from './users'
import { createLogger, errorType } from '../../lib/observability/logger'

const logger = createLogger('session')

/**
 * Owns the active profile, startup error, and retry generation.
 * Mount/retry runs an abortable list-and-activate sequence; switching publishes a
 * new user only after the backend session key is ready.
 * @returns {{user: import('./users').UserProfile|null, error: string,
 * switchUser: (next: import('./users').UserProfile, signal?: AbortSignal) => Promise<void>,
 * retry: () => void}} Session state and recovery/switching actions.
 */
export function useSession() {
  const [user, setUser] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    // 1. Isolate each initialization attempt so cleanup cannot affect a later retry.
    const controller = new AbortController()
    /**
     * Loads and activates the first profile, reporting non-cancellation failures.
     * @returns {Promise<void>} Settles after state publication or visible failure.
     */
    async function initialize() {
      // 2. Load profiles before allocating user-scoped backend conversation state.
      try {
        const users = await listUsers(controller.signal)
        if (!users.length) throw new Error('No users are available.')
        const selected = await activateUser(users[0], controller.signal)
        // 3. Publish only a live attempt's fully activated profile.
        if (!controller.signal.aborted) setUser(selected)
      } catch (error) {
        if (!controller.signal.aborted) {
          logger.error('session.initialize_failed', { error_type: errorType(error) })
          setError(error.message)
        }
      }
    }
    initialize()
    // 4. Cancel superseded/unmounted initialization without reporting it as failure.
    return () => controller.abort()
  }, [attempt])

  /**
   * Activates the requested profile before changing app-wide identity.
   * @param {import('./users').UserProfile} next - Requested profile.
   * @param {AbortSignal} [signal] - Modal-owned cancellation.
   * @returns {Promise<void>} Rejects to the profile dialog on activation failure.
   */
  async function switchUser(next, signal) {
    // 1. Keep the old identity active in the UI until backend activation succeeds.
    const selected = await activateUser(next, signal)
    // 2. Let App's user key reset user-scoped views, unless switching was cancelled.
    if (!signal?.aborted) setUser(selected)
  }

  return { user, error, switchUser,
    /**
     * Restarts list-and-activate initialization without affecting App's health effect.
     * @returns {void}
     */
    retry: () => {
      // 1. Restore the session loading boundary before triggering a new attempt.
      setError('')
      // 2. Change the effect dependency so repeated retries each issue a new request.
      setAttempt((n) => n + 1)
    } }
}
