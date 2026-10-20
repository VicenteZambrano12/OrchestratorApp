/**
 * @file Backend readiness probe used by the application startup gate.
 * Combines caller cancellation with a five-second deadline and requires the
 * orchestrator API's explicit healthy status, not just a successful HTTP code.
 */

/**
 * Checks backend availability before user-scoped feature views mount.
 * @param {AbortSignal} signal - Lifecycle-owned cancellation.
 * @returns {Promise<void>} Resolves only for an HTTP-successful {status: 'ok'} body.
 * @throws {Error} For timeout, cancellation, network/HTTP errors, or unhealthy JSON.
 */
export async function checkHealth(signal) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const response = await observedFetch('/health', `${baseUrl}/health`, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
  })
  if (!response.ok) throw new Error(`Health check returned HTTP ${response.status}`)
  const data = await response.json()
  if (data.status !== 'ok') throw new Error('Backend reported an unhealthy status')
}
import { observedFetch } from '../../lib/observability/http'
