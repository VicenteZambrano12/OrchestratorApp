/**
 * @file Profile, routine, and orchestrator-session HTTP utilities (not React hooks).
 * All calls use instrumented requests and five-second cancellation deadlines.
 * Routine reads validate saved payloads; version writes may include the agent draft
 * confirmation context. Errors reject for caller-owned loading and recovery UI.
 *
 * @typedef {object} UserProfile
 * @property {number} id - Persisted user identifier.
 * @property {string} username - Profile display name; not an authentication credential.
 * @property {'kg'|'lbs'} weight_unit - Preferred workout load unit.
 *
 * @typedef {object} RoutineResult
 * @property {import('../../features/RoutineMaker/routine-data/routineData').RoutinePlan|null} routine - Active routine or no saved plan.
 * @property {number|null} routineId - ID from the X-Routine-Id response header.
 */
import { isRoutinePlan, isSavedRoutinePlan } from '../../features/RoutineMaker/routine-data/routineData'
import { observedFetch } from '../../lib/observability/http'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

/**
 * Requests the profile collection with timeout and duplicate-name error handling.
 * @param {RequestInit} [options={}] - Request method, body, and cancellation.
 * @returns {Promise<UserProfile|UserProfile[]>} Decoded profile response.
 * @throws {Error} For conflicts, HTTP failures, cancellation, or invalid JSON.
 */
async function userRequest(options = {}) {
  const response = await observedFetch('/users', `${baseUrl}/users`, {
    ...options,
    signal: options.signal
      ? AbortSignal.any([options.signal, AbortSignal.timeout(5000)])
      : AbortSignal.timeout(5000),
  })
  if (response.status === 409) throw new Error('That username is already registered.')
  if (!response.ok) throw new Error(`User API returned HTTP ${response.status}`)
  return response.json()
}

/**
 * Loads available local profiles without activating a chat session.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @returns {Promise<UserProfile[]>} Backend profile collection.
 */
export function listUsers(signal) {
  return userRequest({ signal })
}

/**
 * Loads the backend's seven-day activity window; shape validation is downstream.
 * @param {number} userId - Positive persisted user ID.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @returns {Promise<Array<{date: string, has_routine: boolean}>>} Daily workout flags.
 * @throws {Error} For invalid identity or failed HTTP/JSON processing.
 */
export async function getUserDays(userId, signal) {
  if (!Number.isSafeInteger(userId) || userId < 1) {
    throw new Error('Weekly rhythm user ID must be a positive integer.')
  }
  const response = await observedFetch('/users/{user_id}/days', `${baseUrl}/users/${userId}/days`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),
  })
  if (!response.ok) throw new Error(`Weekly rhythm API returned HTTP ${response.status}`)
  return response.json()
}

/**
 * Executes a routine read/write and validates both new and legacy saved plans.
 * @param {number} userId - Positive persisted user ID.
 * @param {RequestInit} options - HTTP method/body configuration.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @param {string} [query=''] - Encoded query including a leading question mark.
 * @param {boolean} [includeMetadata=false] - Requires/exposes the routine identity header.
 * @returns {Promise<import('../../features/RoutineMaker/routine-data/routineData').RoutinePlan|null|RoutineResult>} Validated result.
 * @throws {Error} For invalid IDs, HTTP/JSON failures, invalid plans, or missing metadata.
 */
async function routineRequest(userId, options, signal, query = '', includeMetadata = false) {
  // 1. Reject invalid ownership before sending any routine request.
  if (!Number.isSafeInteger(userId) || userId < 1) {
    throw new Error('Routine user ID must be a positive integer.')
  }
  // 2. Apply the shared request deadline and propagate backend validation details.
  const response = await observedFetch('/users/{user_id}/routine', `${baseUrl}/users/${userId}/routine${query}`, {
    ...options,
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),
  })
  if (!response.ok) {
    const body = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null
    const detail = typeof body?.detail === 'string' ? body.detail :
      Array.isArray(body?.detail) ? body.detail.map((item) => item.msg).join(' ') : ''
    throw new Error(`Routine API returned HTTP ${response.status}${detail ? `: ${detail}` : ''}`)
  }
  // 3. Validate saved-plan shape before exposing it to rendering or workout logging.
  const routine = await response.json()
  if (routine !== null && !isSavedRoutinePlan(routine)) {
    throw new Error('The routine API returned an invalid routine.')
  }
  // 4. Require stable persisted identity when callers need to attach actual workouts.
  if (includeMetadata) {
    const routineId = routine === null ? null : Number(response.headers.get('X-Routine-Id'))
    if (routine !== null && (!Number.isSafeInteger(routineId) || routineId < 1)) {
      throw new Error('The routine API returned no valid routine ID.')
    }
    return { routine, routineId }
  }
  return routine
}

/**
 * Reads the active routine, optionally retaining its persisted version identity.
 * @param {number} userId - Persisted user ID.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @param {object} [options={}] - Result-shape options.
 * @param {boolean} [options.includeMetadata=false] - Returns a RoutineResult wrapper.
 * @returns {Promise<import('../../features/RoutineMaker/routine-data/routineData').RoutinePlan|null|RoutineResult>} Active routine result.
 */
export function getUserRoutine(userId, signal, { includeMetadata = false } = {}) {
  return routineRequest(userId, {}, signal, '', includeMetadata)
}

/**
 * Saves a complete routine as a new active version, optionally confirming an AI draft.
 * @param {number} userId - Routine owner.
 * @param {import('../../features/RoutineMaker/routine-data/routineData').RoutinePlan} routine - New-format plan.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @param {object} [options={}] - Agent context and result-shape options.
 * @param {string} [options.sessionId] - Agent conversation identity.
 * @param {string} [options.draftId] - Required with sessionId to confirm the specific draft.
 * @param {'EN'|'ES'} [options.language] - Required supported language for draft confirmation.
 * @param {boolean} [options.includeMetadata=false] - Exposes persisted routine identity.
 * @returns {Promise<import('../../features/RoutineMaker/routine-data/routineData').RoutinePlan|RoutineResult>} Non-null saved result.
 * @throws {Error} For invalid plans/context or any failed persistence/response validation.
 */
export async function saveUserRoutine(userId, routine, signal, { sessionId, draftId, language, includeMetadata = false } = {}) {
  // 1. Validate the complete plan and the all-or-nothing agent confirmation context.
  if (!isRoutinePlan(routine)) throw new Error('The saved routine is not valid.')
  if ((sessionId !== undefined || draftId !== undefined) &&
    (typeof sessionId !== 'string' || !sessionId.trim() ||
      typeof draftId !== 'string' || !draftId.trim() || !['EN', 'ES'].includes(language))) {
    throw new Error('Routine saves require a session, draft ID, and EN or ES language.')
  }
  // 2. Attach draft context only for agent confirmation; editor saves omit it.
  const query = sessionId === undefined ? '' : `?${new URLSearchParams({
    session_id: sessionId, draft_id: draftId, language,
  })}`
  const saved = await routineRequest(userId, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(routine),
  }, signal, query, includeMetadata)
  // 3. A write must yield a saved plan, not the valid empty result allowed by reads.
  if (saved === null || (includeMetadata && saved.routine === null)) throw new Error('The routine API returned an invalid routine.')
  return saved
}

/**
 * Registers a profile without automatically activating its orchestrator session.
 * @param {string} username - Name trimmed before submission.
 * @param {'kg'|'lbs'} weightUnit - Preferred load unit.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @returns {Promise<UserProfile>} Created profile.
 */
export function registerUser(username, weightUnit, signal) {
  return userRequest({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username.trim(), weight_unit: weightUnit }),
    signal,
  })
}

/**
 * Initializes backend conversation state before exposing a selected profile.
 * @param {UserProfile} user - Profile to activate.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @returns {Promise<UserProfile>} The same profile after session initialization succeeds.
 */
export async function activateUser(user, signal) {
  await setSessionKey(String(user.id), signal)
  return user
}

/**
 * Initializes or explicitly resets orchestrator conversation state for a session.
 * @param {string} id - Session key derived from the selected profile identity.
 * @param {AbortSignal} [signal] - Caller cancellation.
 * @param {boolean} [reset=false] - Requests a fresh backend conversation.
 * @returns {Promise<object>} Decoded backend acknowledgement.
 * @throws {Error} For HTTP, JSON, timeout, or cancellation failures.
 */
export async function setSessionKey(id, signal, reset = false) {
  const response = await observedFetch('/{id}/key', `${baseUrl}/${encodeURIComponent(id)}/key${reset ? '?reset=true' : ''}`, {
    method: 'POST',
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),
  })
  if (!response.ok) throw new Error(`Set key returned HTTP ${response.status}`)
  return response.json()
}
