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
