import { useEffect, useState } from 'react'
import { restSeconds } from './sessionTime'
import { createWorkoutSets } from './workoutSets'

export function useWorkoutSession() {
  const [startedAt, setStartedAt] = useState(null)
  const [now, setNow] = useState(0)
  const [rest, setRest] = useState(null)
  const [sessionError, setSessionError] = useState('')
  const [dayIndex, setDayIndex] = useState(0)
  const [sets, setSets] = useState([])
  const isWorkoutActive = startedAt !== null

  useEffect(() => {
    if (!isWorkoutActive) return
    const timer = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(timer)
  }, [isWorkoutActive])

  function startWorkout(index, exercises) {
    const time = Date.now()
    setNow(time)
    setStartedAt(time)
    setDayIndex(index)
    setSets(createWorkoutSets(exercises))
    setSessionError('')
  }

  function finishWorkout() {
    setStartedAt(null)
    setRest(null)
    setSets([])
    setSessionError('')
  }

  function updateSet(index, field, value) {
    setSets((current) => current.map((set, i) => i === index ? { ...set, [field]: value } : set))
  }

  function startRest(index, duration) {
    try {
      const seconds = restSeconds(duration)
      const time = Date.now()
      setNow(time)
      setRest(seconds > 0 ? { index, endsAt: time + seconds * 1000 } : null)
      setSessionError('')
    } catch (error) {
      setRest(null)
      setSessionError(error instanceof Error ? 'Could not start rest timer. Check the exercise rest duration.' : String(error))
    }
  }

  const remaining = rest ? Math.max(0, Math.ceil((rest.endsAt - now) / 1000)) : 0
  return {
    isWorkoutActive, dayIndex, sets, updateSet, sessionError, startWorkout, finishWorkout, startRest,
    elapsed: isWorkoutActive ? Math.floor((now - startedAt) / 1000) : 0,
    remaining, restIndex: rest?.index,
    skipRest: () => setRest(null),
    extendRest: () => setRest((current) => current ? { ...current, endsAt: Math.max(Date.now(), current.endsAt) + 15000 } : null),
  }
}
