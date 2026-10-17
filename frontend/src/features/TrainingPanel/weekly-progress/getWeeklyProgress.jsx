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
