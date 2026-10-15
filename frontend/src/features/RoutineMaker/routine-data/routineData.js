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

export function toWorkoutRoutine(plan) {
  return {
    name: plan.name,
    summary: plan.summary,
    recovery: plan.recovery,
    days: plan.days.map((day) => ({
      name: day.day_type,
      focus: day.info,
      durationMinutes: day.duration_minutes,
      exercises: day.exercises.map((exercise) => ({
        exerciseId: exercise.exercise_id,
        name: exercise.name,
        sets: exercise.sets,
        reps: exercise.reps,
        rest: `${exercise.rest_seconds}s`,
        notes: exercise.notes,
        weight: 0,
        completed: false,
      })),
    })),
  }
}

export function toRoutinePlan(workout) {
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
