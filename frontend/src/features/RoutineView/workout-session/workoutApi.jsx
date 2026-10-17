const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function saveWorkout(userId, routineId, sets, signal) {
  if (!Number.isSafeInteger(userId) || userId < 1 || !Number.isSafeInteger(routineId) || routineId < 1) {
    throw new Error('A saved user and routine are required to record a workout.')
  }
  const response = await fetch(`${baseUrl}/users/${userId}/workouts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ routine_id: routineId, sets }),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  })
  if (!response.ok) {
    const body = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null
    const detail = typeof body?.detail === 'string' ? body.detail :
      Array.isArray(body?.detail) ? body.detail.map((item) => item.msg).join(' ') : ''
    throw new Error(`Workout API returned HTTP ${response.status}${detail ? `: ${detail}` : ''}`)
  }
  const result = await response.json()
  if (typeof result?.training_id !== 'string' || !result.training_id ||
    result.user_id !== userId || result.routine_id !== routineId || result.sets_saved !== sets.length ||
    !/^\d{4}-\d{2}-\d{2}$/.test(result.date) || !Number.isFinite(Date.parse(result.created_at))) {
    throw new Error('The workout API returned an invalid response.')
  }
  return result
}
