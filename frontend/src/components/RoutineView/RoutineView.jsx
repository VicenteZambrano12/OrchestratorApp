/**
 * @file Interactive routine workspace composing target editing, exercise selection,
 * local workout timing, and confirmation dialogs. Planned targets and performed
 * sets stay separate; persistence is delegated through callbacks from MainView.
 */
import { Fragment, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowLeftRight, ArrowRight, ArrowUp, Check, CheckCheck, Clock3, Dumbbell, GripVertical, Play, Plus, Sparkles, Square, Target, Trash2 } from 'lucide-react'
import { useWorkoutEditor } from '../../features/RoutineView/workout-editing/useWorkoutEditor'
import { toggleExerciseCompletion } from '../../features/RoutineView/workout-completion/toggleExerciseCompletion'
import { formatTime } from '../../features/RoutineView/workout-session/sessionTime'
import { filledWorkoutSets, workoutSetsError } from '../../features/RoutineView/workout-session/workoutSets'
import ExerciseDialog from './ExerciseDialog'
import ExerciseValueInput from './ExerciseValueInput'
import RoutineUpdateDialog from './RoutineUpdateDialog'
import WorkoutFinishDialog from './WorkoutFinishDialog'
import './RoutineView.css'

/**
 * Renders a controlled routine with a day locked while a workout is active.
 * Requires translations; local state tracks selection, dialogs, and save feedback.
 * Legacy routines permit workout logging but disable structural editing.
 * @param {object} props - Routine workspace properties.
 * @param {import('../../features/RoutineMaker/routine-data/routineData').WorkoutRoutine} props.routine - Controlled draft.
 * @param {Function} props.setRoutine - Publishes immutable draft changes.
 * @param {(prompt: string) => void} props.onAsk - Opens AI chat with an adjustment prompt.
 * @param {Function} [props.onSave] - Optional locally valid draft notification.
 * @param {Function} [props.onUpdate] - Persists a routine version; rejection keeps editing open.
 * @param {Function} [props.onFinishWorkout] - Persists normalized actual sets before session teardown.
 * @param {ReturnType<import('../../features/RoutineView/workout-session/useWorkoutSession').useWorkoutSession>} props.workoutSession - Shared active-session state/actions.
 * @param {string} [props.weightUnit='kg'] - Display unit; does not convert stored loads.
 * @param {boolean} [props.saved] - Whether to display routine save feedback.
 * @param {string} [props.error] - Parent-owned persistence error.
 * @param {string} [props.savedMessage='Changes saved on this device.'] - Save feedback translation key.
 * @returns {import('react').ReactElement} Routine editor, workout controls, and active dialogs.
 */
export default function RoutineView({ routine, setRoutine, onAsk, onSave, onUpdate, onFinishWorkout, workoutSession: session, weightUnit = 'kg', saved, error, savedMessage = 'Changes saved on this device.' }) {
  const { t } = useTranslation()
  const [selectedDayIndex, setDayIndex] = useState(0)
  // Exercise/set indices must continue referring to the same day until it is saved.
  const dayIndex = session.isWorkoutActive ? session.dayIndex : selectedDayIndex
  const [exerciseDialog, setExerciseDialog] = useState(null)
  const [confirmUpdate, setConfirmUpdate] = useState(false)
  const [confirmFinish, setConfirmFinish] = useState(false)
  const [workoutRecorded, setWorkoutRecorded] = useState(false)
  const dialogIndex = exerciseDialog?.index ?? null
  const dragIndex = useRef(null)
  const dialogTrigger = useRef(null)
  const editButtonRef = useRef(null)
  const workoutButtonRef = useRef(null)
  const { isEditing, validation, toggleEditing, changeExercise, addExercise, swapExercise, removeExercise, reorderExercise } =
    useWorkoutEditor({ routine, dayIndex, setRoutine, onSave })
  const day = routine.days[dayIndex]
  const complete = day.exercises.filter((exercise) => exercise.completed).length
  // Completion is exercise-level; only filled sets from Done exercises may be saved.
  const completedSets = session.isWorkoutActive ? filledWorkoutSets(session.sets.filter((set) => day.exercises[set.exerciseIndex].completed)) : []
  const workoutValidation = session.isWorkoutActive && complete > 0 ? workoutSetsError(completedSets) : ''
  const nextExercise = day.exercises.findIndex((exercise) => !exercise.completed)
  const suggestions = [...new Map(routine.days.flatMap((item) => item.exercises.map((exercise) => [exercise.name, exercise]))).values()]

  /** @returns {void} Requests version-save confirmation only for a valid edited routine. */
  function finishEditing() {
    // 1. Keep persistence explicit; otherwise let editor validation govern mode exit.
    if (isEditing && onUpdate && !validation) setConfirmUpdate(true)
    else toggleEditing()
  }

  /** @returns {void} Closes version confirmation and restores the triggering control's focus. */
  function closeUpdate() {
    setConfirmUpdate(false)
    editButtonRef.current?.focus()
  }

  /**
   * Persists the current draft before leaving edit mode.
   * @returns {Promise<void>} Rejects to RoutineUpdateDialog so edits remain recoverable.
   */
  async function updateRoutine() {
    // 1. Let the parent save a new backend version before changing editor state.
    await onUpdate(routine)
    // 2. Exit and restore focus only after confirmed persistence.
    toggleEditing()
    closeUpdate()
  }

  /**
   * Changes selection only outside an active workout.
   * @param {number} index - Zero-based day index.
   * @returns {void}
   */
  function selectDay(index) {
    // 1. Preserve active-session identity; clear drag state when selection changes.
    if (!session.isWorkoutActive && index !== dayIndex) {
      setDayIndex(index)
      dragIndex.current = null
    }
  }

  /** @returns {void} Resets local completion and starts actual-set capture for the selected day. */
  function startWorkout() {
    // 1. Clear previous success/completion without modifying planned targets.
    setWorkoutRecorded(false)
    setRoutine({
      ...routine,
      days: routine.days.map((item, index) => index === dayIndex
        ? { ...item, exercises: item.exercises.map((exercise) => ({ ...exercise, completed: false })) } : item),
    })
    // 2. Lock this day and allocate performed-set inputs in the session hook.
    session.startWorkout(dayIndex, day.exercises)
  }

  /** @returns {void} Closes workout confirmation and restores focus to the workout control. */
  function closeFinish() {
    setConfirmFinish(false)
    workoutButtonRef.current?.focus()
  }

  /**
   * Completes a session only after its selected actual sets have been persisted.
   * @param {Array<{exercise_id: number, reps: number, weight: number|null}>} sets - Normalized performed sets.
   * @returns {Promise<void>} Rejects to the dialog without clearing workout inputs.
   */
  async function finishWorkout(sets) {
    // 1. Keep the workout active while the parent saves its history.
    await onFinishWorkout(sets)
    // 2. Release the day lock and show success only after the API acknowledges it.
    setDayIndex(dayIndex)
    session.finishWorkout()
    setWorkoutRecorded(true)
    closeFinish()
  }

  /**
   * Updates local completion and coordinates the exercise-specific rest timer.
   * @param {number} index - Exercise index in the selected day.
   * @returns {void}
   */
  function completeExercise(index) {
    // 1. Publish immutable completion and notify optional valid-draft consumers.
    const next = toggleExerciseCompletion(routine, dayIndex, index)
    setRoutine(next)
    if (!validation) onSave?.(next)
    // 2. Start known rest on completion, or clear rest when its exercise is undone.
    if (session.isWorkoutActive && next.days[dayIndex].exercises[index].completed && day.exercises[index].rest !== null) session.startRest(index, day.exercises[index].rest)
    else if (session.restIndex === index) session.skipRest()
  }

  /**
   * Applies an allowed exercise move and discards index-bound rest state.
   * @param {number|null} from - Drag source or keyboard source index.
   * @param {number} to - Destination index.
   * @returns {void}
   */
  function reorder(from, to) {
    // 1. Ignore invalid/no-op gestures before publishing a new exercise ordering.
    if (from === null || from === to || to < 0 || to >= day.exercises.length) return
    reorderExercise(from, to)
    // 2. A rest timer cannot follow an index whose exercise has moved.
    session.skipRest()
  }

  /**
   * Opens add/swap selection and retains its trigger for accessible focus recovery.
   * @param {import('react').MouseEvent<HTMLButtonElement>} event - Trigger activation.
   * @param {number|null} [index=null] - Swap target; null means add.
   * @returns {void}
   */
  function openDialog(event, index = null) {
    dialogTrigger.current = event.currentTarget
    setExerciseDialog({ index })
  }

  /** @returns {void} Closes exercise selection and restores focus to its trigger. */
  function closeDialog() {
    setExerciseDialog(null)
    dialogTrigger.current?.focus()
  }

  /**
   * Applies a selection with add defaults or editor-controlled swap resets.
   * @param {{name: string, exerciseId: number|null, rest: string}} replacement - Selected exercise identity/timing.
   * @returns {void}
   */
  function confirmExercise(replacement) {
    // 1. Add with initial targets or retain existing targets through the swap action.
    if (dialogIndex === null) addExercise({ ...replacement, sets: 3, reps: '8–12', weight: 0, completed: false, notes: '' })
    else swapExercise(dialogIndex, replacement)
    // 2. Clear obsolete rest timing and return focus to the editor.
    session.skipRest()
    closeDialog()
  }

  /**
   * Implements roving tab focus while enforcing the active-workout day lock.
   * @param {import('react').KeyboardEvent<HTMLButtonElement>} event - Day-tab key event.
   * @param {number} index - Current tab index.
   * @returns {void}
   */
  function onTabKey(event, index) {
    // 1. Suppress navigation keys while actual-set indices depend on the active day.
    if (session.isWorkoutActive) {
      if (['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) event.preventDefault()
      return
    }
    // 2. Resolve wraparound/Home/End navigation only for supported tab keys.
    const count = routine.days.length
    const next = { ArrowRight: (index + 1) % count, ArrowLeft: (index - 1 + count) % count, Home: 0, End: count - 1 }[event.key]
    if (next === undefined) return
    event.preventDefault()
    // 3. Synchronize selected content and keyboard focus.
    selectDay(next)
    document.getElementById(`day-tab-${next}`)?.focus()
  }

  return <div className="routine-view">
    <div className="section-heading"><div><span className="eyebrow">{t('YOUR PERSONAL PLAYBOOK')}</span><h1>{routine.name || t('A plan for your potential')}<span>.</span></h1><p>{routine.summary || t("Show up for yourself. We'll handle the next step.")}</p>
      <div className="routine-badges">
        <span><Dumbbell size={13} /><span className="sr-only">{t('Training split')}: </span>{routine.name ? [...new Set(routine.days.map((item) => item.name))].join(' / ') : t('Push / Pull / Legs')}</span>
        <span><Clock3 size={13} /><span className="sr-only">{t('Session length')}: </span>{day.durationMinutes === null ? t('Unknown') : day.durationMinutes ? `${day.durationMinutes} ${t('min')}` : t('60 minutes')}</span>
        <span><Target size={13} />{t('trainingDayCount', { count: routine.days.length })}</span>
        {!routine.name && <span>{t('Demo workout')}</span>}
      </div>
    </div><span className="plan-badge"><span className="status-dot" />{t('Active plan')}</span></div>
    {routine.storageFormat === 'legacy' && <p role="status">{t('Legacy workout templates: timing is unknown. You can log workouts; create a new plan to edit timing and structure.')}</p>}
    <div className="day-tabs" role="tablist" aria-label={t('Workout days')}>{routine.days.map((item, index) => <button key={index} id={`day-tab-${index}`} role="tab" aria-selected={index === dayIndex} aria-controls="day-panel" disabled={session.isWorkoutActive && index !== dayIndex} tabIndex={index === dayIndex ? 0 : -1} onKeyDown={(event) => onTabKey(event, index)} onClick={() => selectDay(index)}>
      <span className="day-tab-top"><span>{t('DAY')} {String(index + 1).padStart(2, '0')}</span><span className="day-completion">{t('dayCompletion', { completed: item.exercises.filter((exercise) => exercise.completed).length, total: item.exercises.length })}</span></span>
      <strong>{t(item.name)}</strong><small className="line-clamp-1" title={t(item.focus)}>{t(item.focus)}</small>
    </button>)}</div>
    <section className="workout-card" id="day-panel" role="tabpanel" aria-labelledby={`day-tab-${dayIndex}`}>
      <div className="workout-heading"><div><span className="eyebrow">{t('DAY')} {dayIndex + 1}, {t("LET'S DO THIS")}</span><h2>{t('workoutDay', { day: t(day.name) })} <span>{t('exercises', { count: day.exercises.length })}</span></h2></div>
        <div className="button-group workout-actions"><button ref={editButtonRef} className={`secondary-button ${isEditing ? 'done-editing' : ''}`} aria-pressed={isEditing} disabled={session.isWorkoutActive || routine.storageFormat === 'legacy'} onClick={finishEditing}>{isEditing && <Check size={15} />}{t(isEditing ? 'Done editing' : 'Edit workout')}</button>
          <button ref={workoutButtonRef} className="start-workout" disabled={Boolean(validation || workoutValidation) || (!session.isWorkoutActive && (isEditing || day.exercises.length === 0 || !onFinishWorkout))} onClick={session.isWorkoutActive ? () => setConfirmFinish(true) : startWorkout}>{session.isWorkoutActive ? <Square size={15} /> : <Play size={15} fill="currentColor" />}{t(session.isWorkoutActive ? 'Finish workout' : 'Start Workout')}</button>
        </div>
      </div>
      {session.isWorkoutActive && <div className="session-status"><span><Clock3 size={16} />{t('Session timer')} <time aria-label={t('Elapsed time')}>{formatTime(session.elapsed)}</time></span><span>{t('dayCompletion', { completed: complete, total: day.exercises.length })}</span></div>}
      {session.isWorkoutActive && <p className="workout-day-lock" role="status">{t('Finish and save this workout before switching days.')}</p>}
      {session.isWorkoutActive && <p className="workout-day-lock">{t('Enter reps for the sets you perform, then mark the exercise Done. Leave skipped sets and exercises blank. Weight is optional.')}</p>}
      <div className="workout-progress" role="progressbar" aria-label={t('Exercises completed')} aria-valuemin={0} aria-valuemax={Math.max(1, day.exercises.length)} aria-valuenow={complete}><span style={{ width: `${day.exercises.length ? complete / day.exercises.length * 100 : 0}%` }} /></div>
      <div className="exercise-table-scroll"><div className={`exercise-table ${isEditing ? 'is-editing' : ''}`}>
        <div className="exercise-table-head"><span>{t('EXERCISE')}</span><span>{t('SETS')}</span><span>{t('REPS')}</span><span>{weightUnit.toUpperCase()}</span><span>{t('DONE')}</span>{isEditing && <span className="sr-only">{t('Exercise actions')}</span>}</div>
        {day.exercises.map((exercise, index) => <Fragment key={`${exercise.name}-${index}`}><div className={`exercise-row ${exercise.completed ? 'completed' : ''} ${session.isWorkoutActive && index === nextExercise ? 'next-exercise' : ''}`}
          onDragOver={(event) => { if (isEditing && dragIndex.current !== null) { event.preventDefault(); event.dataTransfer.dropEffect = 'move' } }}
          onDrop={(event) => { event.preventDefault(); if (isEditing) reorder(dragIndex.current, index); dragIndex.current = null }}>
          <div className="exercise-name">
            {isEditing && <button type="button" className="exercise-grip" draggable aria-label={t('Reorder {{exercise}}', { exercise: t(exercise.name) })} title={t('Drag or use arrow keys to reorder')}
              onDragStart={(event) => { dragIndex.current = index; event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', String(index)) }}
              onDragEnd={() => { dragIndex.current = null }}
              onKeyDown={(event) => { if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); const target = index + (event.key === 'ArrowUp' ? -1 : 1); reorder(index, target); requestAnimationFrame(() => document.querySelectorAll('.exercise-grip')[Math.max(0, Math.min(day.exercises.length - 1, target))]?.focus()) } }}>
              <GripVertical size={17} />
            </button>}
            <span className="exercise-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{t(exercise.name)}</strong><small>{exercise.muscle && <>{t(exercise.muscle)} · </>}{t('restDuration', { duration: exercise.rest === null ? t('Unknown') : t(exercise.rest) })}</small>{exercise.notes && <small>{exercise.notes}</small>}</span>
          </div>
          {['sets', 'reps', 'weight'].map((field) => <span key={field}>{session.isWorkoutActive ? exercise[field] : <ExerciseValueInput exercise={exercise} field={field} weightUnit={weightUnit} onChange={(value) => changeExercise(index, field, value)} />}</span>)}
          <button className={`completion-button ${exercise.completed ? 'checked' : ''}`} role="checkbox" aria-label={t(exercise.completed ? 'Mark {{exercise}} incomplete' : 'Mark {{exercise}} complete', { exercise: t(exercise.name) })} aria-checked={exercise.completed} onClick={() => completeExercise(index)}>{exercise.completed && <Check size={16} strokeWidth={3} />}</button>
          {isEditing && <div className="exercise-actions">
            <button className="icon-button" disabled={index === 0} aria-label={t('Move {{exercise}} up', { exercise: t(exercise.name) })} title={t('Move up')} onClick={() => reorder(index, index - 1)}><ArrowUp size={15} /></button>
            <button className="icon-button" disabled={index === day.exercises.length - 1} aria-label={t('Move {{exercise}} down', { exercise: t(exercise.name) })} title={t('Move down')} onClick={() => reorder(index, index + 1)}><ArrowDown size={15} /></button>
            <button className="icon-button" aria-label={t('Swap {{exercise}}', { exercise: t(exercise.name) })} title={t('Swap exercise')} onClick={(event) => openDialog(event, index)}><ArrowLeftRight size={16} /></button>
            <button className="icon-button remove-exercise" aria-label={t('Remove {{exercise}}', { exercise: t(exercise.name) })} title={t('Remove exercise')} onClick={() => { removeExercise(index); session.skipRest() }}><Trash2 size={16} /></button>
          </div>}
        </div>
        {session.isWorkoutActive && <div className="workout-exercise-sets">
          {session.sets.map((set, setIndex) => set.exerciseIndex === index && <fieldset key={setIndex}>
            <legend>{t('{{exercise}} — Set {{number}}', { exercise: t(set.name), number: set.setNumber })}</legend>
            <div className="workout-set-inputs">
              <label>{t('Actual reps')}<input type="number" min="1" step="1" value={set.reps}
                aria-label={t('{{exercise}} set {{number}} reps', { exercise: t(set.name), number: set.setNumber })}
                onChange={(event) => session.updateSet(setIndex, 'reps', event.target.value)} /></label>
              <label>{t('Weight ({{unit}})', { unit: weightUnit })}<input type="number" min="0" step="any" value={set.weight}
                aria-label={t('{{exercise}} set {{number}} weight', { exercise: t(set.name), number: set.setNumber })}
                onChange={(event) => session.updateSet(setIndex, 'weight', event.target.value)} /></label>
            </div>
          </fieldset>)}
        </div>}
        </Fragment>)}
      </div></div>
      {isEditing && <button className="add-exercise" onClick={(event) => openDialog(event)}><Plus size={17} />{t('Add exercise to {{day}}', { day: t(day.name) })}</button>}
      {session.remaining > 0 && <div className="rest-countdown" role="group" aria-label={t('Rest countdown')}><span><Clock3 size={16} />{t('Rest')} <time role="timer">{formatTime(session.remaining)}</time></span><button onClick={session.extendRest} aria-label={t('Add 15 seconds of rest')}>+15s</button><button onClick={session.skipRest}>{t('Skip')}</button></div>}
      <div className="workout-footer"><span><CheckCheck size={17} />{t('exerciseCompletion', { completed: complete, total: day.exercises.length })}</span><span>{t('Warm up before you start. Make every rep count.')}</span></div>
    </section>
    {(validation || workoutValidation || error || session.sessionError) && <p role="alert" className="error-message">{validation ? t(validation) : workoutValidation ? t(workoutValidation) : error || t(session.sessionError)}</p>}
    {saved && !validation && !workoutValidation && <p className="save-message" role="status"><Check size={15} />{t(savedMessage)}</p>}
    {workoutRecorded && <p className="save-message" role="status"><Check size={15} />{t('Workout saved successfully.')}</p>}
    {routine.recovery && <p>{routine.recovery}</p>}
    <div className="routine-coach-banner"><span className="tip-icon"><Sparkles size={24} /></span><div><h3>{t("Your routine isn't set in stone.")}</h3><p>{t('Different schedule? New goal? Your coach can help you adapt.')}</p></div><button className="primary-button" onClick={() => onAsk(t('Help me update my routine to fit my schedule.'))}>{t('Adjust with AI')} <ArrowRight size={16} /></button></div>
    {exerciseDialog && <ExerciseDialog exercise={dialogIndex === null ? null : day.exercises[dialogIndex]} suggestions={suggestions} onConfirm={confirmExercise} onClose={closeDialog} />}
    {confirmUpdate && <RoutineUpdateDialog onConfirm={updateRoutine} onClose={closeUpdate} />}
    {confirmFinish && <WorkoutFinishDialog sets={completedSets} onConfirm={finishWorkout} onClose={closeFinish} />}
  </div>
}
