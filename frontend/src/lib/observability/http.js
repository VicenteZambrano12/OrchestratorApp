/**
 * @file Instrumentation wrappers for frontend HTTP and asynchronous operations.
 * Measures elapsed time without recording request bodies or raw URLs. HTTP
 * responses retain native semantics; network/operation errors are classified,
 * logged, and rethrown so feature code remains responsible for visible recovery.
 */
import { createLogger, errorType } from './logger.js'

const logger = createLogger('http')
const operations = createLogger('operations')

/**
 * Distinguishes deadline expiry, intentional cancellation, and unexpected failures.
 * @param {unknown} error - Rejected operation value.
 * @param {AbortSignal|null} [signal] - Operation cancellation context.
 * @returns {{level: 'warn'|'debug'|'error', outcome: 'timeout'|'cancelled'|'failed'}} Log classification.
 */
function failure(error, signal) {
  if (error?.name === 'TimeoutError' || (signal?.aborted && signal.reason?.name === 'TimeoutError')) {
    return { level: 'warn', outcome: 'timeout' }
  }
  if (error?.name === 'AbortError' || signal?.aborted) return { level: 'debug', outcome: 'cancelled' }
  return { level: 'error', outcome: 'failed' }
}

/**
 * Measures fetch through response headers while preserving its response/error value.
 * @param {string} route - Static route template without user IDs or query parameters.
 * @param {RequestInfo|URL} input - Actual fetch destination; excluded from log fields.
 * @param {RequestInit} [options={}] - Native fetch options and caller-owned signal.
 * @returns {Promise<Response>} Response including non-success HTTP statuses.
 * @throws {Error} Rethrows transport/cancellation failures after logging.
 */
export async function observedFetch(route, input, options = {}) {
  // 1. Capture request timing and only non-sensitive method/route metadata.
  const started = performance.now()
  const method = (options.method ?? 'GET').toUpperCase()
  try {
    // 2. Preserve HTTP response semantics; callers validate status and payload.
    const response = await fetch(input, options)
    const severity = response.status >= 500 ? 'error' : response.status >= 400 ? 'warn' : 'info'
    logger[severity]('http.response', {
      method, route, status: response.status,
      duration_ms: performance.now() - started, outcome: response.ok ? 'success' : 'failed',
    })
    return response
  } catch (error) {
    // 3. Log safe failure classification and rethrow for feature-owned error UI.
    const { level, outcome } = failure(error, options.signal)
    logger[level]('http.failure', {
      method, route, duration_ms: performance.now() - started, outcome, error_type: errorType(error),
    })
    throw error
  }
}

/**
 * Measures an asynchronous operation, including stream decoding through completion.
 * The supplied signal classifies failures; it does not itself cancel operation.
 * @template T
 * @param {string} event - Static operation label.
 * @param {() => Promise<T>} operation - Work that manages its own cancellation.
 * @param {AbortSignal} [signal] - Failure classification context.
 * @returns {Promise<T>} Unchanged operation result.
 * @throws {Error} Rethrows operation failures after safe logging.
 */
export async function observeOperation(event, operation, signal) {
  const started = performance.now()
  try {
    const result = await operation()
    operations.info(event, { duration_ms: performance.now() - started, outcome: 'success' })
    return result
  } catch (error) {
    const { level, outcome } = failure(error, signal)
    operations[level](event, { duration_ms: performance.now() - started, outcome, error_type: errorType(error) })
    throw error
  }
}
