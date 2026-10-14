import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowRight, Check, CheckCheck, Clock3, Dumbbell, Sparkles, Target } from 'lucide-react'
import { SubsystemResponse } from '../../features/ai-chat/components/SubsystemResponse'
import { useWorkoutEditor } from '../../features/RoutineView/workout-editing/useWorkoutEditor'
import { toggleExerciseCompletion } from '../../features/RoutineView/workout-completion/toggleExerciseCompletion'

export default function RoutineView({ routine, setRoutine, onAsk, onSave, saved, error }) {
  const { t } = useTranslation()
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
    <div className="section-heading"><div><span className="eyebrow">{t('YOUR PERSONAL PLAYBOOK')}</span><h1>{t('A plan for your potential')}<span>.</span></h1><p>{t("Show up for yourself. We'll handle the next step.")}</p></div><span className="plan-badge"><span className="status-dot" />{t('Active plan')}</span></div>
    <div className="routine-summary"><div><Dumbbell size={20} /><span><small>{t('Training split')}</small><strong>{t('Push / Pull / Legs')}</strong></span></div><div><Clock3 size={20} /><span><small>{t('Session length')}</small><strong>{t('60 minutes')}</strong></span></div><div><Target size={20} /><span><small>{t('Your focus')}</small><strong>{t('Build strength')}</strong></span></div><span className="demo-label">{t('Demo workout')}</span></div>
    {routine.generated && <section className="generated-routine"><div><Sparkles size={18} /><h3>{t('Latest coach recommendation')}</h3></div><p>{t('Review this recommendation alongside your editable workout. It does not automatically replace your exercise log.')}</p><SubsystemResponse subsystem="routine_maker" content={routine.generated} /></section>}
    <div className="day-tabs" role="tablist" aria-label={t('Workout days')}>{displayed.days.map((item, index) => <button key={item.name} id={`day-tab-${index}`} role="tab" aria-selected={index === dayIndex} aria-controls="day-panel" tabIndex={index === dayIndex ? 0 : -1} onKeyDown={(event) => onTabKey(event, index)} onClick={() => setDayIndex(index)}><span>{t('DAY')} 0{index + 1}</span><strong>{t(item.name)}</strong><small>{t(item.focus)}</small></button>)}</div>
    <section className="workout-card" id="day-panel" role="tabpanel" aria-labelledby={`day-tab-${dayIndex}`}>
      <div className="workout-heading"><div><span className="eyebrow">{t(['MONDAY', 'WEDNESDAY', 'FRIDAY'][dayIndex])}, {t("LET'S DO THIS")}</span><h2>{t('workoutDay', { day: t(day.name) })} <span>{t('exercises', { count: day.exercises.length })}</span></h2></div>{editing ? <div className="button-group"><button className="text-button" onClick={cancelEditing}>{t('Cancel')}</button><button className="primary-button" onClick={saveEdits}><Check size={15} />{t('Save changes')}</button></div> : <button className="secondary-button" onClick={startEditing}>{t('Edit workout')}</button>}</div>
      <div className="workout-progress" role="progressbar" aria-label={t('Exercises completed')} aria-valuemin={0} aria-valuemax={day.exercises.length} aria-valuenow={complete}><span style={{ width: `${day.exercises.length ? complete / day.exercises.length * 100 : 0}%` }} /></div>
      <div className="exercise-table"><div className="exercise-table-head"><span>{t('EXERCISE')}</span><span>{t('SETS')}</span><span>{t('REPS')}</span><span>KG</span><span>{t('DONE')}</span></div>
        {day.exercises.map((exercise, index) => <div className={`exercise-row ${exercise.completed ? 'completed' : ''}`} key={`${exercise.name}-${index}`}><div className="exercise-name"><span className="exercise-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{t(exercise.name)}</strong><small>{t(exercise.muscle)} · {t('restDuration', { duration: t(exercise.rest) })}</small></span></div>{['sets', 'reps', 'weight'].map((field) => <span key={field}>{editing ? <input aria-label={`${t(exercise.name)} ${t(field)}`} type={field === 'reps' ? 'text' : 'number'} min={field === 'sets' ? 1 : 0} max={field === 'sets' ? 10 : undefined} step={field === 'weight' ? 0.5 : 1} value={exercise[field]} onChange={(event) => changeExercise(index, field, event.target.value)} /> : exercise[field]}</span>)}<button className={`completion-button ${exercise.completed ? 'checked' : ''}`} aria-label={t(exercise.completed ? 'Mark {{exercise}} incomplete' : 'Mark {{exercise}} complete', { exercise: t(exercise.name) })} aria-pressed={exercise.completed} disabled={editing} onClick={() => completeExercise(index)}><Check size={15} /></button></div>)}
      </div>
      <div className="workout-footer"><span><CheckCheck size={17} />{t('exerciseCompletion', { completed: complete, total: day.exercises.length })}</span><span>{t('Warm up before you start. Make every rep count.')}</span></div>
    </section>
    {(validation || error) && <p role="alert" className="error-message">{validation ? t(validation) : error}</p>}
    {saved && <p className="save-message" role="status"><Check size={15} />{t('Changes saved on this device.')}</p>}
    <div className="routine-coach-banner"><span className="tip-icon"><Sparkles size={24} /></span><div><h3>{t("Your routine isn't set in stone.")}</h3><p>{t('Different schedule? New goal? Your coach can help you adapt.')}</p></div><button className="primary-button" onClick={() => onAsk(t('Help me update my routine to fit my schedule.'))}>{t('Adjust with AI')} <ArrowRight size={16} /></button></div>
  </div>
}
