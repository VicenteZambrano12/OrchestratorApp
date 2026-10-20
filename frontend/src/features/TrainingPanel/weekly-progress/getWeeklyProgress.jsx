/**
 * @file Validated seven-day activity adapter for the training sidebar.
 * Uses UTC calendar arithmetic to avoid browser timezone shifts and rejects gaps,
 * duplicate dates, and impossible dates instead of presenting misleading activity.
 */

/**
 * Sorts a complete consecutive seven-day backend window and counts logged days.
 * @param {Array<{date: string, has_routine: boolean}>} days - Backend activity rows.
 * @returns {{completed: number, weekDays: Array<{date: string, weekdayIndex: number,
 * isTrainingDay: boolean}>}} Monday-based weekday indices and workout presence.
 * @throws {Error} If the payload is not seven valid, consecutive calendar days.
 */
export function getWeeklyProgress(days) {
  if (!Array.isArray(days) || days.length !== 7 || days.some((day) =>
    !day || typeof day.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(day.date) ||
    typeof day.has_routine !== 'boolean' ||
    !Number.isFinite(Date.parse(`${day.date}T00:00:00Z`)))) {
    throw new Error('The weekly rhythm API returned invalid days.')
  }
  const ordered = [...days].sort((a, b) => a.date.localeCompare(b.date))
  const weekDays = ordered.map((day, index) => {
    const date = new Date(`${day.date}T00:00:00Z`)
    if (date.toISOString().slice(0, 10) !== day.date ||
      (index > 0 && date.getTime() - Date.parse(`${ordered[index - 1].date}T00:00:00Z`) !== 86400000)) {
      throw new Error('The weekly rhythm API returned invalid days.')
    }
    return {
      date: day.date,
      weekdayIndex: (date.getUTCDay() + 6) % 7,
      isTrainingDay: day.has_routine,
    }
  })
  return {
    completed: weekDays.filter((day) => day.isTrainingDay).length,
    weekDays,
  }
}
