export function isRoutinePlan(plan) {
  return Boolean(plan && typeof plan.name === 'string' && plan.name.trim() &&
    typeof plan.recovery === 'string' && plan.recovery.trim() &&
    (plan.summary === undefined || (typeof plan.summary === 'string' && plan.summary.length <= 600)) &&
    Array.isArray(plan.days) && plan.days.length >= 1 && plan.days.length <= 7 &&
    plan.days.every((day, index) =>
      day && day.day === index + 1 && typeof day.day_type === 'string' && day.day_type.trim() &&
      typeof day.info === 'string' && day.info.trim() &&
      Number.isFinite(day.duration_minutes) && day.duration_minutes > 0 &&
      Array.isArray(day.exercises) && day.exercises.length > 0 &&
      new Set(day.exercises.map((item) => item?.exercise_id)).size === day.exercises.length &&
      day.exercises.every((item) =>
        item && Number.isSafeInteger(item.exercise_id) && item.exercise_id > 0 &&
        typeof item.name === 'string' && item.name.trim() &&
        Number.isInteger(item.sets) && item.sets >= 1 && item.sets <= 20 &&
        typeof item.reps === 'string' && item.reps.trim() &&
        Number.isInteger(item.rest_seconds) && item.rest_seconds >= 0 && item.rest_seconds <= 900 &&
        typeof item.notes === 'string')))
}
