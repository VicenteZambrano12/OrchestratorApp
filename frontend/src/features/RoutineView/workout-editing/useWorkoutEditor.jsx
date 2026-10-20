/**
 * @file Controlled workout-editor hook coordinating immutable target changes.
 * Invalid drafts remain editable, but the optional save callback receives only
 * plans whose exercise targets validate. Backend persistence belongs to the caller.
 */
import { useState } from 'react'
import { isValidExercise, updateDayExercises, moveExercise } from './workoutEditing'

/**
 * Derives validation from the supplied routine and owns only edit-mode state.
 * @param {object} options - Controlled editor dependencies.
 * @param {import('../../RoutineMaker/routine-data/routineData').WorkoutRoutine} options.routine - Current draft.
 * @param {number} options.dayIndex - Day affected by editing actions.
 * @param {(routine: import('../../RoutineMaker/routine-data/routineData').WorkoutRoutine) => void} options.setRoutine - Draft setter.
 * @param {Function} [options.onSave] - Receives a locally valid draft; not necessarily a server save.
 * @returns {{isEditing: boolean, validation: string, toggleEditing: Function,
 * changeExercise: Function, addExercise: Function, swapExercise: Function,
 * removeExercise: Function, reorderExercise: Function}} Validation and immutable editor actions.
 */
export function useWorkoutEditor({ routine, dayIndex, setRoutine, onSave }) {
  const [isEditing, setIsEditing] = useState(false)
  const validation = routine.days.some((day) => day.exercises.some((exercise) => !isValidExercise(exercise)))
    ? 'Enter 1–20 sets, a rep target, and a weight of at least 0 kg.' : ''

  /**
   * Publishes the selected-day draft and notifies the caller only when valid.
   * @param {Function} update - Immutable exercise-array transformation.
   * @returns {void}
   */
  function updateExercises(update) {
    // 1. Publish edits immediately so invalid drafts remain visible and correctable.
    const next = updateDayExercises(routine, dayIndex, update)
    setRoutine(next)
    // 2. Notify save consumers only when all days' target fields are valid.
    if (next.days.every((day) => day.exercises.every(isValidExercise))) onSave?.(next)
  }

  /**
   * Changes one target while retaining the rest of the selected day's exercises.
   * @param {number} index - Exercise index.
   * @param {'sets'|'reps'|'weight'} field - Editable field.
   * @param {number|string} value - Raw or normalized input.
   * @returns {void}
   */
  function changeExercise(index, field, value) {
    updateExercises((exercises) => exercises.map((exercise, i) => i === index ? { ...exercise, [field]: value } : exercise))
  }

  /** @returns {void} Enters editing freely but prevents exit with invalid targets. */
  function toggleEditing() {
    if (!isEditing || !validation) setIsEditing(!isEditing)
  }

  return {
    isEditing, validation, toggleEditing, changeExercise,
    /**
     * Appends a draft exercise to the selected day.
     * @param {import('../../RoutineMaker/routine-data/routineData').WorkoutExercise} exercise - Initial targets.
     * @returns {void}
     */
    addExercise: (exercise) => updateExercises((exercises) => [...exercises, exercise]),
    /**
     * Replaces identity/timing while retaining targets and clearing exercise-specific state.
     * @param {number} index - Selected-day exercise index.
     * @param {{name: string, exerciseId: number|null, rest: string}} replacement - New selection.
     * @returns {void}
     */
    swapExercise: (index, replacement) => updateExercises((exercises) => exercises.map((exercise, i) => i === index
      ? { ...exercise, ...replacement, weight: 0, completed: false, muscle: '', notes: '' } : exercise)),
    /**
     * Removes an exercise from the controlled draft without mutating other days.
     * @param {number} index - Selected-day exercise index.
     * @returns {void}
     */
    removeExercise: (index) => updateExercises((exercises) => exercises.filter((_, i) => i !== index)),
    /**
     * Applies the shared immutable ordering helper to the selected day.
     * @param {number} from - Source index.
     * @param {number} to - Destination index.
     * @returns {void}
     */
    reorderExercise: (from, to) => updateExercises((exercises) => moveExercise(exercises, from, to)),
  }
}
