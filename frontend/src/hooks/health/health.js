export async function checkHealth(signal) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const response = await fetch(`${baseUrl}/health`, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
  })
  if (!response.ok) throw new Error(`Health check returned HTTP ${response.status}`)
  const data = await response.json()
  if (data.status !== 'ok') throw new Error('Backend reported an unhealthy status')
}
