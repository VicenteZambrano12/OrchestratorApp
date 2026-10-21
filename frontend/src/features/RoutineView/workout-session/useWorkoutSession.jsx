/**
 * @file Local workout-session state and wall-clock-based rest timing.
 * This hook does not persist workouts: the view saves performed sets through the
 * backend API before calling finishWorkout to discard the active session.
 */
import { useEffect, useState } from 'react'
import { restSeconds } from './sessionTime'
import { createWorkoutSets } from './workoutSets'

/**
 * Owns the locked day, actual set inputs, elapsed clock, and optional rest timer.
 * A 250 ms tick runs only during an active workout; remaining time derives from
 * absolute deadlines so delayed browser ticks do not accumulate timer drift.
 * @returns {{isWorkoutActive: boolean, dayIndex: number,
 * sets: import('./workoutSets').WorkoutSet[], updateSet: Function,
 * sessionError: string, startWorkout: Function, finishWorkout: Function,
 * startRest: Function, elapsed: number, remaining: number, restIndex: number|undefined,
 * skipRest: () => void, extendRest: () => void}} Session state and local actions.
 */
export function useWorkoutSession() {
  // Null distinguishes no workout from an active session with zero elapsed time.
  const [startedAt, setStartedAt] = useState(null)
  const [now, setNow] = useState(0)
  const [rest, setRest] = useState(null)
  const [sessionError, setSessionError] = useState('')
  const [dayIndex, setDayIndex] = useState(0)
  const [sets, setSets] = useState([])
  const isWorkoutActive = startedAt !== null

  useEffect(() => {
    // 1. Avoid allocating a clock while no workout is active.
    if (!isWorkoutActive) return
    // 2. Refresh wall-clock state and release the interval when the session ends.
    const timer = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(timer)
  }, [isWorkoutActive])

  /**
   * Locks a day and initializes actual-set inputs from its exercise targets.
   * @param {number} index - Zero-based day index.
   * @param {import('../../RoutineMaker/routine-data/routineData').WorkoutExercise[]} exercises - Day targets.
   * @returns {void}
   */
  function startWorkout(index, exercises) {
    // 1. Capture a shared start timestamp for elapsed time and the first render.
    const time = Date.now()
    setNow(time)
    setStartedAt(time)
    // 2. Lock day identity and create independent performed-set input state.
    setDayIndex(index)
    setSets(createWorkoutSets(exercises))
    setSessionError('')
  }

  /** @returns {void} Clears local session state after the caller confirms persistence. */
  function finishWorkout() {
    // 1. Stop the clock and rest timer only after the owning view has saved.
    setStartedAt(null)
    setRest(null)
    setSets([])
    setSessionError('')
  }

  /**
   * Updates one performed-set input without modifying planned exercise targets.
   * @param {number} index - Flat set index.
   * @param {'reps'|'weight'} field - Editable actual-set field.
   * @param {string} value - Uncoerced input value.
   * @returns {void}
   */
  function updateSet(index, field, value) {
    setSets((current) => current.map((set, i) => i === index ? { ...set, [field]: value } : set))
  }

  /**
   * Starts a rest deadline for a completed exercise or exposes invalid timing.
   * @param {number} index - Exercise associated with rest.
   * @param {string} duration - Unit-suffixed planned rest.
   * @returns {void}
   */
  function startRest(index, duration) {
    // 1. Parse explicit units before creating a wall-clock deadline.
    try {
      const seconds = restSeconds(duration)
      const time = Date.now()
      setNow(time)
      setRest(seconds > 0 ? { index, endsAt: time + seconds * 1000 } : null)
      setSessionError('')
    } catch (error) {
      // 2. Clear unusable timer state and surface the error to the workout view.
      setRest(null)
      setSessionError(error instanceof Error ? 'Could not start rest timer. Check the exercise rest duration.' : String(error))
    }
  }

  const remaining = rest ? Math.max(0, Math.ceil((rest.endsAt - now) / 1000)) : 0
  return {
    isWorkoutActive, dayIndex, sets, updateSet, sessionError, startWorkout, finishWorkout, startRest,
    elapsed: isWorkoutActive ? Math.floor((now - startedAt) / 1000) : 0,
    remaining, restIndex: rest?.index,
    /** @returns {void} Discards the optional exercise-bound rest deadline. */
    skipRest: () => setRest(null),
    /**
     * Adds 15 seconds from the later of now or the current rest deadline.
     * Does not create a timer when no rest period exists.
     * @returns {void}
     */
    extendRest: () => setRest((current) => current ? { ...current, endsAt: Math.max(Date.now(), current.endsAt) + 15000 } : null),
  }
}
