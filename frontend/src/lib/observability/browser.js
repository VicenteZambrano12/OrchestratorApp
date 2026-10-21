/**
 * @file Lifecycle-managed global browser error/rejection instrumentation.
 * Deduplicates registration per window, sanitizes errors to class names, and
 * exposes disposal for hot reload. Logging does not suppress native error events.
 */
import { createLogger, errorType } from './logger.js'

const logger = createLogger('browser')
const registrations = new WeakMap()

/**
 * Registers one global error/rejection listener pair for a browser window.
 * @param {Window} [target=window] - Event target to instrument.
 * @returns {() => void} Existing or newly created listener-disposal callback.
 */
export function initializeObservability(target = window) {
  // 1. Reuse existing registration instead of duplicating global error reports.
  if (registrations.has(target)) return registrations.get(target)
  /**
   * Records only the safe error class for uncaught synchronous failures.
   * @param {ErrorEvent} event - Native uncaught-error notification.
   * @returns {void}
   */
  const onError = (event) => logger.error('browser.uncaught_error', { error_type: errorType(event.error) })
  /**
   * Separates expected abort rejections from unexpected asynchronous failures.
   * @param {PromiseRejectionEvent} event - Unhandled promise rejection.
   * @returns {void}
   */
  const onRejection = (event) => {
    // 2. Classify cancellations without exposing the rejected message or payload.
    if (event.reason?.name === 'AbortError') {
      logger.debug('browser.unhandled_rejection', { error_type: 'AbortError', outcome: 'cancelled' })
    } else {
      logger.error('browser.unhandled_rejection', { error_type: errorType(event.reason) })
    }
  }
  // 3. Attach both listeners and retain a stable cleanup function for hot reload.
  target.addEventListener('error', onError)
  target.addEventListener('unhandledrejection', onRejection)
  /** @returns {void} Removes listeners and permits future registration on the target. */
  const dispose = () => {
    target.removeEventListener('error', onError)
    target.removeEventListener('unhandledrejection', onRejection)
    registrations.delete(target)
  }
  registrations.set(target, dispose)
  return dispose
}
