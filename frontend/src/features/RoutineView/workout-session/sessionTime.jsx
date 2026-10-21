/** @file Pure parsing and display helpers for workout elapsed/rest timers. */

/**
 * Parses explicit second/minute units and rounds to whole seconds.
 * @param {string} duration - Unit-suffixed duration, such as "90 sec" or "2 min".
 * @returns {number} Non-negative duration in seconds.
 * @throws {Error} If the value has no supported numeric/unit representation.
 */
export function restSeconds(duration) {
  const match = String(duration).trim().match(/^(\d+(?:\.\d+)?)\s*(s|sec|seconds?|m|min|minutes?)$/i)
  if (!match) throw new Error(`Invalid rest duration: ${duration}`)
  return Math.round(Number(match[1]) * (/^m/i.test(match[2]) ? 60 : 1))
}

/**
 * Formats a duration as minutes and seconds, clamping negative values to zero.
 * @param {number} seconds - Elapsed or remaining seconds.
 * @returns {string} Zero-padded minute:second display; minutes may exceed 59.
 */
export function formatTime(seconds) {
  const value = Math.max(0, Math.floor(seconds))
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
}
