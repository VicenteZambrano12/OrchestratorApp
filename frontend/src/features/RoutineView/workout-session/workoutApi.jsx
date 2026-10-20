/**
 * @file Workout persistence API boundary using instrumented HTTP requests.
 * Enforces user/routine identity and a 15-second timeout, then checks the server's
 * saved-set receipt. Failures reject so the UI retains the active workout for retry.
 */
const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

/**
 * Records performed sets against a saved routine and validates the acknowledgement.
 * @param {number} userId - Positive persisted user ID.
 * @param {number} routineId - Positive persisted routine ID.
 * @param {Array<{exercise_id: number, reps: number, weight: number|null}>} sets - Validated actual sets.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @returns {Promise<{training_id: string, user_id: number, routine_id: number,
 * sets_saved: number, date: string, created_at: string}>} Server workout receipt.
 * @throws {Error} For invalid IDs, HTTP errors, cancellation/timeout, or invalid receipts.
 */
export async function saveWorkout(userId, routineId, sets, signal) {
  // 1. Reject missing persisted identities before writing workout history.
  if (!Number.isSafeInteger(userId) || userId < 1 || !Number.isSafeInteger(routineId) || routineId < 1) {
    throw new Error('A saved user and routine are required to record a workout.')
  }
  // 2. POST the performed sets with combined caller cancellation and timeout.
  const response = await observedFetch('/users/{user_id}/workouts', `${baseUrl}/users/${userId}/workouts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ routine_id: routineId, sets }),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  })
  // 3. Preserve backend validation details for the caller's visible save error.
  if (!response.ok) {
    const body = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null
    const detail = typeof body?.detail === 'string' ? body.detail :
      Array.isArray(body?.detail) ? body.detail.map((item) => item.msg).join(' ') : ''
    throw new Error(`Workout API returned HTTP ${response.status}${detail ? `: ${detail}` : ''}`)
  }
  // 4. Require matching identities and set counts before the UI ends the workout.
  const result = await response.json()
  if (typeof result?.training_id !== 'string' || !result.training_id ||
    result.user_id !== userId || result.routine_id !== routineId || result.sets_saved !== sets.length ||
    !/^\d{4}-\d{2}-\d{2}$/.test(result.date) || !Number.isFinite(Date.parse(result.created_at))) {
    throw new Error('The workout API returned an invalid response.')
  }
  return result
}
import { observedFetch } from '../../../lib/observability/http'
