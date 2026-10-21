/**
 * @file Structured, level-filtered browser logging with an allowlisted metadata set.
 * Error messages, prompts, raw URLs, payloads, and model output are not copied into
 * log records. Callers provide static event/scope names and templated route names.
 */
const levels = { debug: 10, info: 20, warn: 30, error: 40, off: Infinity }
let level = import.meta.env?.VITE_LOG_LEVEL ?? (import.meta.env?.DEV ? 'debug' : 'warn')

/**
 * Sets the shared logger threshold, including explicit off mode.
 * @param {'debug'|'info'|'warn'|'error'|'off'} next - Minimum emitted severity.
 * @returns {void}
 * @throws {RangeError} For unsupported levels, including invalid environment settings.
 */
export function configureLogging(next) {
  if (!Object.hasOwn(levels, next)) throw new RangeError('Log level must be debug, info, warn, error, or off.')
  level = next
}

configureLogging(level)

/**
 * Reduces an unknown thrown value to an allowlisted error name without its message.
 * @param {unknown} error - Thrown/rejected value.
 * @returns {string} Known error class name or UnknownError.
 */
export function errorType(error) {
  const name = error?.name
  return ['Error', 'TypeError', 'RangeError', 'SyntaxError', 'ReferenceError', 'URIError',
    'EvalError', 'AggregateError', 'AbortError', 'TimeoutError', 'SecurityError',
    'QuotaExceededError'].includes(name) ? name : 'UnknownError'
}

/**
 * Creates immutable severity methods sharing the current global log threshold.
 * @param {string} scope - Static module/subsystem label.
 * @returns {Readonly<{debug: Function, info: Function, warn: Function, error: Function}>} Structured logging methods accepting event and optional metadata.
 */
export function createLogger(scope) {
  /**
   * Emits finite numeric/string allowlisted fields to the matching console method.
   * @param {'debug'|'info'|'warn'|'error'} severity - Record level.
   * @param {string} event - Static event identifier.
   * @param {object} [metadata={}] - Candidate metadata; non-allowlisted keys are discarded.
   * @returns {void}
   */
  function log(severity, event, metadata = {}) {
    if (levels[severity] < levels[level]) return
    const fields = {}
    for (const key of ['method', 'route', 'status', 'duration_ms', 'outcome', 'error_type']) {
      if (typeof metadata[key] === 'string' || (typeof metadata[key] === 'number' && Number.isFinite(metadata[key]))) {
        fields[key] = metadata[key]
      }
    }
    console[severity]({
      timestamp: new Date().toISOString(), level: severity, scope, event, ...fields,
    })
  }
  return Object.freeze({
    /**
     * Records low-severity diagnostics when enabled.
     * @param {string} event - Static event identifier.
     * @param {object} [metadata] - Allowlisted scalar diagnostic fields.
     * @returns {void}
     */
    debug: (event, metadata) => log('debug', event, metadata),
    /**
     * Records successful request/operation lifecycle events when enabled.
     * @param {string} event - Static event identifier.
     * @param {object} [metadata] - Allowlisted scalar diagnostic fields.
     * @returns {void}
     */
    info: (event, metadata) => log('info', event, metadata),
    /**
     * Records recoverable failures or degraded conditions when enabled.
     * @param {string} event - Static event identifier.
     * @param {object} [metadata] - Allowlisted scalar diagnostic fields.
     * @returns {void}
     */
    warn: (event, metadata) => log('warn', event, metadata),
    /**
     * Records unexpected operation failures when enabled.
     * @param {string} event - Static event identifier.
     * @param {object} [metadata] - Allowlisted scalar diagnostic fields.
     * @returns {void}
     */
    error: (event, metadata) => log('error', event, metadata),
  })
}
