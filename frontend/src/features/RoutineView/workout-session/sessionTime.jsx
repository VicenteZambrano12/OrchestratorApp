export function restSeconds(duration) {
  const match = String(duration).trim().match(/^(\d+(?:\.\d+)?)\s*(s|sec|seconds?|m|min|minutes?)$/i)
  if (!match) throw new Error(`Invalid rest duration: ${duration}`)
  return Math.round(Number(match[1]) * (/^m/i.test(match[2]) ? 60 : 1))
}

export function formatTime(seconds) {
  const value = Math.max(0, Math.floor(seconds))
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
}
