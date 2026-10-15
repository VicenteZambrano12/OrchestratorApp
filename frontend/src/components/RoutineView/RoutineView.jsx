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

export default function RoutineView({ routine, setRoutine, onAsk, onSave, onUpdate, onFinishWorkout, workoutSession: session, weightUnit = 'kg', saved, error, savedMessage = 'Changes saved on this device.' }) {
  const { t } = useTranslation()
  const [selectedDayIndex, setDayIndex] = useState(0)
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
  const completedSets = session.isWorkoutActive ? filledWorkoutSets(session.sets.filter((set) => day.exercises[set.exerciseIndex].completed)) : []
  const workoutValidation = session.isWorkoutActive && complete > 0 ? workoutSetsError(completedSets) : ''
  const nextExercise = day.exercises.findIndex((exercise) => !exercise.completed)
  const suggestions = [...new Map(routine.days.flatMap((item) => item.exercises.map((exercise) => [exercise.name, exercise]))).values()]

  function finishEditing() {
    if (isEditing && onUpdate && !validation) setConfirmUpdate(true)
    else toggleEditing()
  }

  function closeUpdate() {
    setConfirmUpdate(false)
    editButtonRef.current?.focus()
  }

  async function updateRoutine() {
    await onUpdate(routine)
    toggleEditing()
    closeUpdate()
  }

  function selectDay(index) {
    if (!session.isWorkoutActive && index !== dayIndex) {
      setDayIndex(index)
      dragIndex.current = null
    }
  }

  function startWorkout() {
    setWorkoutRecorded(false)
    setRoutine({
      ...routine,
      days: routine.days.map((item, index) => index === dayIndex
        ? { ...item, exercises: item.exercises.map((exercise) => ({ ...exercise, completed: false })) } : item),
    })
    session.startWorkout(dayIndex, day.exercises)
  }

  function closeFinish() {
    setConfirmFinish(false)
    workoutButtonRef.current?.focus()
  }

  async function finishWorkout(sets) {
    await onFinishWorkout(sets)
    setDayIndex(dayIndex)
    session.finishWorkout()
    setWorkoutRecorded(true)
    closeFinish()
  }

  function completeExercise(index) {
    const next = toggleExerciseCompletion(routine, dayIndex, index)
    setRoutine(next)
    if (!validation) onSave?.(next)
    if (session.isWorkoutActive && next.days[dayIndex].exercises[index].completed && day.exercises[index].rest !== null) session.startRest(index, day.exercises[index].rest)
    else if (session.restIndex === index) session.skipRest()
  }

  function reorder(from, to) {
    if (from === null || from === to || to < 0 || to >= day.exercises.length) return
    reorderExercise(from, to)
    session.skipRest()
  }

  function openDialog(event, index = null) {
    dialogTrigger.current = event.currentTarget
    setExerciseDialog({ index })
  }

  function closeDialog() {
    setExerciseDialog(null)
    dialogTrigger.current?.focus()
  }

  function confirmExercise(replacement) {
    if (dialogIndex === null) addExercise({ ...replacement, sets: 3, reps: '8–12', weight: 0, completed: false, notes: '' })
    else swapExercise(dialogIndex, replacement)
    session.skipRest()
    closeDialog()
  }

  function onTabKey(event, index) {
    if (session.isWorkoutActive) {
      if (['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) event.preventDefault()
      return
    }
    const count = routine.days.length
    const next = { ArrowRight: (index + 1) % count, ArrowLeft: (index - 1 + count) % count, Home: 0, End: count - 1 }[event.key]
    if (next === undefined) return
    event.preventDefault()
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
