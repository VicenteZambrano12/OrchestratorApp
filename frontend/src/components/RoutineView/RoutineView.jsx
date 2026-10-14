import { useState } from 'react'
import { ArrowRight, Check, CheckCheck, Clock3, Dumbbell, Sparkles, Target } from 'lucide-react'
import { SubsystemResponse } from '../../features/ai-chat/components/SubsystemResponse'
import { useWorkoutEditor } from '../../features/RoutineView/workout-editing/useWorkoutEditor'
import { toggleExerciseCompletion } from '../../features/RoutineView/workout-completion/toggleExerciseCompletion'

export default function RoutineView({ routine, setRoutine, onAsk, onSave, saved, error }) {
  const [dayIndex, setDayIndex] = useState(0)
  const { editing, displayed, validation, startEditing, cancelEditing, changeExercise, saveEdits } =
    useWorkoutEditor({ routine, dayIndex, setRoutine, onSave })
  const day = displayed.days[dayIndex]
  const complete = day.exercises.filter((exercise) => exercise.completed).length

  function completeExercise(index) {
    const next = toggleExerciseCompletion(routine, dayIndex, index)
    setRoutine(next)
    onSave(next)
  }

  function onTabKey(event, index) {
    const count = displayed.days.length
    const next = { ArrowRight: (index + 1) % count, ArrowLeft: (index - 1 + count) % count, Home: 0, End: count - 1 }[event.key]
    if (next === undefined) return
    event.preventDefault()
    setDayIndex(next)
    document.getElementById(`day-tab-${next}`)?.focus()
  }

  return <div className="routine-view">
    <div className="section-heading"><div><span className="eyebrow">YOUR PERSONAL PLAYBOOK</span><h1>A plan for your potential<span>.</span></h1><p>Show up for yourself. We&apos;ll handle the next step.</p></div><span className="plan-badge"><span className="status-dot" />Active plan</span></div>
    <div className="routine-summary"><div><Dumbbell size={20} /><span><small>Training split</small><strong>Push / Pull / Legs</strong></span></div><div><Clock3 size={20} /><span><small>Session length</small><strong>60 minutes</strong></span></div><div><Target size={20} /><span><small>Your focus</small><strong>Build strength</strong></span></div><span className="demo-label">Demo workout</span></div>
    {routine.generated && <section className="generated-routine"><div><Sparkles size={18} /><h3>Latest coach recommendation</h3></div><p>Review this recommendation alongside your editable workout. It does not automatically replace your exercise log.</p><SubsystemResponse subsystem="routine_maker" content={routine.generated} /></section>}
    <div className="day-tabs" role="tablist" aria-label="Workout days">{displayed.days.map((item, index) => <button key={item.name} id={`day-tab-${index}`} role="tab" aria-selected={index === dayIndex} aria-controls="day-panel" tabIndex={index === dayIndex ? 0 : -1} onKeyDown={(event) => onTabKey(event, index)} onClick={() => setDayIndex(index)}><span>DAY 0{index + 1}</span><strong>{item.name}</strong><small>{item.focus}</small></button>)}</div>
    <section className="workout-card" id="day-panel" role="tabpanel" aria-labelledby={`day-tab-${dayIndex}`}>
      <div className="workout-heading"><div><span className="eyebrow">{['MONDAY', 'WEDNESDAY', 'FRIDAY'][dayIndex]}, LET&apos;S DO THIS</span><h2>{day.name} day <span>{day.exercises.length} exercises</span></h2></div>{editing ? <div className="button-group"><button className="text-button" onClick={cancelEditing}>Cancel</button><button className="primary-button" onClick={saveEdits}><Check size={15} />Save changes</button></div> : <button className="secondary-button" onClick={startEditing}>Edit workout</button>}</div>
      <div className="workout-progress" role="progressbar" aria-label="Exercises completed" aria-valuemin={0} aria-valuemax={day.exercises.length} aria-valuenow={complete}><span style={{ width: `${day.exercises.length ? complete / day.exercises.length * 100 : 0}%` }} /></div>
      <div className="exercise-table"><div className="exercise-table-head"><span>EXERCISE</span><span>SETS</span><span>REPS</span><span>KG</span><span>DONE</span></div>
        {day.exercises.map((exercise, index) => <div className={`exercise-row ${exercise.completed ? 'completed' : ''}`} key={`${exercise.name}-${index}`}><div className="exercise-name"><span className="exercise-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{exercise.name}</strong><small>{exercise.muscle} · {exercise.rest} rest</small></span></div>{['sets', 'reps', 'weight'].map((field) => <span key={field}>{editing ? <input aria-label={`${exercise.name} ${field}`} type={field === 'reps' ? 'text' : 'number'} min={field === 'sets' ? 1 : 0} max={field === 'sets' ? 10 : undefined} step={field === 'weight' ? 0.5 : 1} value={exercise[field]} onChange={(event) => changeExercise(index, field, event.target.value)} /> : exercise[field]}</span>)}<button className={`completion-button ${exercise.completed ? 'checked' : ''}`} aria-label={`Mark ${exercise.name} ${exercise.completed ? 'incomplete' : 'complete'}`} aria-pressed={exercise.completed} disabled={editing} onClick={() => completeExercise(index)}><Check size={15} /></button></div>)}
      </div>
      <div className="workout-footer"><span><CheckCheck size={17} />{complete} of {day.exercises.length} exercises completed</span><span>Warm up before you start. Make every rep count.</span></div>
    </section>
    {(validation || error) && <p role="alert" className="error-message">{validation || error}</p>}
    {saved && <p className="save-message" role="status"><Check size={15} />Changes saved on this device.</p>}
    <div className="routine-coach-banner"><span className="tip-icon"><Sparkles size={24} /></span><div><h3>Your routine isn&apos;t set in stone.</h3><p>Different schedule? New goal? Your coach can help you adapt.</p></div><button className="secondary-button" onClick={() => onAsk('Help me update my routine to fit my schedule.')}>Adjust with AI <ArrowRight size={16} /></button></div>
  </div>
}
