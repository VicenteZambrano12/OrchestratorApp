export function isRoutinePlan(plan) {
  return plan?.storage_format !== 'legacy' && validatePlan(plan, false)
}

export function isSavedRoutinePlan(plan) {
  return plan?.storage_format === 'legacy' ? validatePlan(plan, true) : isRoutinePlan(plan)
}

export function getPlannedSessionMinutes(day) {
  if (day.duration_minutes !== null) return day.duration_minutes
  // Older templates lack timing: allow 5 minutes to warm up, 45 seconds per
  // working set, 90 seconds between sets, and 1 minute between exercises.
  const seconds = day.exercises.reduce((total, exercise) =>
    total + exercise.sets * 45 + (exercise.sets - 1) * (exercise.rest_seconds ?? 90), 300)
  return Math.ceil((seconds + (day.exercises.length - 1) * 60) / 60)
}

function validatePlan(plan, legacy) {
  return Boolean(plan && typeof plan.name === 'string' && plan.name.trim() &&
    typeof plan.recovery === 'string' && plan.recovery.trim() &&
    (plan.summary === undefined || (typeof plan.summary === 'string' && plan.summary.length <= 600)) &&
    Array.isArray(plan.days) && plan.days.length >= 1 && (legacy || plan.days.length <= 7) &&
    plan.days.every((day, index) =>
      day && day.day === index + 1 && typeof day.day_type === 'string' && day.day_type.trim() &&
      typeof day.info === 'string' && day.info.trim() &&
      (legacy ? Number.isSafeInteger(day.routine_id) && day.routine_id > 0 && day.duration_minutes === null :
        Number.isFinite(day.duration_minutes) && day.duration_minutes > 0) &&
      Array.isArray(day.exercises) && day.exercises.length > 0 &&
      (legacy || new Set(day.exercises.map((item) => item?.exercise_id)).size === day.exercises.length) &&
      day.exercises.every((item) =>
        item && Number.isSafeInteger(item.exercise_id) && item.exercise_id > 0 &&
        typeof item.name === 'string' && item.name.trim() &&
        Number.isInteger(item.sets) && item.sets >= 1 && item.sets <= 20 &&
        typeof item.reps === 'string' && item.reps.trim() &&
        (legacy ? item.rest_seconds === null :
          Number.isInteger(item.rest_seconds) && item.rest_seconds >= 0 && item.rest_seconds <= 900) &&
        typeof item.notes === 'string')))
}

export function toWorkoutRoutine(plan) {
  return {
    name: plan.name,
    summary: plan.summary,
    recovery: plan.recovery,
    ...(plan.storage_format === 'legacy' ? { storageFormat: 'legacy' } : {}),
    days: plan.days.map((day) => ({
      name: day.day_type,
      focus: day.info,
      durationMinutes: day.duration_minutes,
      ...(plan.storage_format === 'legacy' ? { routineId: day.routine_id } : {}),
      exercises: day.exercises.map((exercise) => ({
        exerciseId: exercise.exercise_id,
        name: exercise.name,
        sets: exercise.sets,
        reps: exercise.reps,
        rest: exercise.rest_seconds === null ? null : `${exercise.rest_seconds}s`,
        notes: exercise.notes,
        weight: 0,
        completed: false,
      })),
    })),
  }
}

export function toRoutinePlan(workout) {
  if (workout.storageFormat === 'legacy') {
    throw new Error('Legacy workout templates are read-only. Create a new complete plan to save changes.')
  }
  const plan = {
    name: workout.name,
    summary: workout.summary,
    recovery: workout.recovery,
    days: workout.days.map((day, index) => ({
      day: index + 1,
      day_type: day.name,
      info: day.focus,
      duration_minutes: day.durationMinutes,
      exercises: day.exercises.map((exercise) => {
        if (!Number.isSafeInteger(exercise.exerciseId) || exercise.exerciseId < 1) {
          throw new Error('Custom exercises cannot be saved. Choose an exercise from the routine suggestions.')
        }
        return {
          exercise_id: exercise.exerciseId,
          name: exercise.name,
          sets: Number(exercise.sets),
          reps: exercise.reps,
          rest_seconds: restSeconds(exercise.rest),
          notes: exercise.notes,
        }
      }),
    })),
  }
  if (!isRoutinePlan(plan)) {
    throw new Error('The edited routine is not valid. Each day needs exercises with valid targets and no duplicates.')
  }
  return plan
}
import { restSeconds } from '../../RoutineView/workout-session/sessionTime'
