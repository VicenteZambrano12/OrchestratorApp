import { isRoutinePlan } from '../../features/RoutineMaker/routine-data/routineData'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

async function userRequest(options = {}) {
  const response = await fetch(`${baseUrl}/users`, {
    ...options,
    signal: options.signal
      ? AbortSignal.any([options.signal, AbortSignal.timeout(5000)])
      : AbortSignal.timeout(5000),
  })
  if (response.status === 409) throw new Error('That username is already registered.')
  if (!response.ok) throw new Error(`User API returned HTTP ${response.status}`)
  return response.json()
}

export function listUsers(signal) {
  return userRequest({ signal })
}

async function routineRequest(userId, options, signal, query = '', includeMetadata = false) {
  if (!Number.isSafeInteger(userId) || userId < 1) {
    throw new Error('Routine user ID must be a positive integer.')
  }
  const response = await fetch(`${baseUrl}/users/${userId}/routine${query}`, {
    ...options,
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),
  })
  if (!response.ok) {
    const body = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null
    const detail = typeof body?.detail === 'string' ? body.detail :
      Array.isArray(body?.detail) ? body.detail.map((item) => item.msg).join(' ') : ''
    throw new Error(`Routine API returned HTTP ${response.status}${detail ? `: ${detail}` : ''}`)
  }
  const routine = await response.json()
  if (routine !== null && !isRoutinePlan(routine)) {
    throw new Error('The routine API returned an invalid routine.')
  }
  if (includeMetadata) {
    const routineId = routine === null ? null : Number(response.headers.get('X-Routine-Id'))
    if (routine !== null && (!Number.isSafeInteger(routineId) || routineId < 1)) {
      throw new Error('The routine API returned no valid routine ID.')
    }
    return { routine, routineId }
  }
  return routine
}

export function getUserRoutine(userId, signal, { includeMetadata = false } = {}) {
  return routineRequest(userId, {}, signal, '', includeMetadata)
}

export async function saveUserRoutine(userId, routine, signal, { sessionId, draftId, language, includeMetadata = false } = {}) {
  if (!isRoutinePlan(routine)) throw new Error('The saved routine is not valid.')
  if ((sessionId !== undefined || draftId !== undefined) &&
    (typeof sessionId !== 'string' || !sessionId.trim() ||
      typeof draftId !== 'string' || !draftId.trim() || !['EN', 'ES'].includes(language))) {
    throw new Error('Routine saves require a session, draft ID, and EN or ES language.')
  }
  const query = sessionId === undefined ? '' : `?${new URLSearchParams({
    session_id: sessionId, draft_id: draftId, language,
  })}`
  const saved = await routineRequest(userId, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(routine),
  }, signal, query, includeMetadata)
  if (saved === null || (includeMetadata && saved.routine === null)) throw new Error('The routine API returned an invalid routine.')
  return saved
}

export function registerUser(username, weightUnit, signal) {
  return userRequest({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username.trim(), weight_unit: weightUnit }),
    signal,
  })
}

export async function activateUser(user, signal) {
  await setSessionKey(String(user.id), signal)
  return user
}

export async function setSessionKey(id, signal, reset = false) {
  const response = await fetch(`${baseUrl}/${encodeURIComponent(id)}/key${reset ? '?reset=true' : ''}`, {
    method: 'POST',
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),
  })
  if (!response.ok) throw new Error(`Set key returned HTTP ${response.status}`)
  return response.json()
}
