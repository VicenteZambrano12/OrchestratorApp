import { useId, useState } from 'react'
import { Calendar, Clock3, Dumbbell, HelpCircle, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import './RoutineMaker.css'

export default function RoutineMaker({ routine, onExplainExercise }) {
  const { t } = useTranslation()
  const [activeDay, setActiveDay] = useState(0)
  const id = useId()
  const day = routine.days[activeDay]
  const durations = routine.days.map((item) => item.duration_minutes)
  const min = Math.min(...durations)
  const max = Math.max(...durations)

  function onTabKey(event, index) {
    const count = routine.days.length
    const next = {
      ArrowRight: (index + 1) % count, ArrowLeft: (index - 1 + count) % count,
      Home: 0, End: count - 1,
    }[event.key]
    if (next === undefined) return
    event.preventDefault()
    setActiveDay(next)
    document.getElementById(`${id}-day-${next}`)?.focus()
  }

  return <section className="routine-maker" aria-label={routine.name}>
    <header className="routine-maker-header">
      <span className="routine-maker-badge"><Sparkles size={14} aria-hidden="true" />{t('Routine maker')}</span>
      <h3>{routine.name}</h3>
      {routine.summary && <p>{routine.summary}</p>}
      <dl className="routine-maker-metrics">
        <div><Dumbbell size={18} aria-hidden="true" /><dt>{t('Training split')}</dt><dd>{[...new Set(routine.days.map((item) => item.day_type))].join(' / ')}</dd></div>
        <div><Calendar size={18} aria-hidden="true" /><dt>{t('Training days')}</dt><dd>{routine.days.length}</dd></div>
        <div><Clock3 size={18} aria-hidden="true" /><dt>{t('Session length')}</dt><dd>{min === max ? min : `${min}-${max}`} {t('min')}</dd></div>
      </dl>
    </header>
    <div className="routine-maker-tabs" role="tablist" aria-label={t('Workout days')}>
      {routine.days.map((item, index) => <button key={item.day} type="button"
        role="tab" id={`${id}-day-${index}`} aria-selected={activeDay === index}
        aria-controls={`${id}-panel`} tabIndex={activeDay === index ? 0 : -1}
        onClick={() => setActiveDay(index)} onKeyDown={(event) => onTabKey(event, index)}>
        <small>{t('DAY')} {String(item.day).padStart(2, '0')}</small>
        <strong>{item.day_type}</strong>
        <span>{item.duration_minutes} {t('min')}</span>
      </button>)}
    </div>
    <section className="routine-maker-day" id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-day-${activeDay}`}>
      <p>{day.info}</p>
      <div className="routine-maker-table-scroll">
        <table>
          <caption>{t('workoutDay', { day: day.day_type })}</caption>
          <thead><tr><th scope="col">{t('EXERCISE')}</th><th scope="col">{t('SETS')}</th><th scope="col">{t('REPS')}</th><th scope="col">{t('Rest')}</th></tr></thead>
          <tbody>{day.exercises.map((exercise, index) => <tr key={exercise.exercise_id}>
            <th scope="row"><div className="routine-maker-exercise">
              <span className="routine-maker-number">{String(index + 1).padStart(2, '0')}</span>
              <div><strong>{exercise.name}</strong>{exercise.notes && <p>{exercise.notes}</p>}</div>
              {onExplainExercise && <button type="button" className="icon-button"
                aria-label={t('Explain {{exercise}}', { exercise: exercise.name })}
                onClick={() => onExplainExercise(exercise.name)}><HelpCircle size={17} aria-hidden="true" /></button>}
            </div></th>
            <td>{exercise.sets}</td><td>{exercise.reps}</td><td>{exercise.rest_seconds}s</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
    <footer className="routine-maker-recovery"><Sparkles size={16} aria-hidden="true" /><p>{routine.recovery}</p></footer>
  </section>
}
