import { useEffect, useState } from 'react'
import { v4 as uuidv4 } from 'uuid'

export async function setSessionKey(id, signal) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const response = await fetch(`${baseUrl}/${encodeURIComponent(id)}/key`, {
    method: 'POST',
    signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
  })
  if (!response.ok) throw new Error(`Set key returned HTTP ${response.status}`)
  return response.json()
}

// Generates a new session id on every mount (page open/refresh) and registers it in the backend.
export function useSession() {
  const [sessionId] = useState(() => uuidv4())

  useEffect(() => {
    const controller = new AbortController()
    setSessionKey(sessionId, controller.signal).catch((error) => {
      if (!controller.signal.aborted) console.error('Failed to set session key', error)
    })
    return () => controller.abort()
  }, [sessionId])

  return sessionId
}
