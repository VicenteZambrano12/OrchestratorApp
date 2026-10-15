import { ArrowRight, Dumbbell, Sparkles, Target } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import BrandMark from '../BrandMark/BrandMark'
import { getWeeklyProgress } from '../../features/TrainingPanel/weekly-progress/getWeeklyProgress'
import { getUserDays, getUserRoutine } from '../../hooks/session/users'
import { getPlannedSessionMinutes } from '../../features/RoutineMaker/routine-data/routineData'

export default function TrainingPanel({ userId, routineRevision, onOpen, onPrompt }) {
  const { t } = useTranslation()
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [routine, setRoutine] = useState(undefined)
  const [routineError, setRoutineError] = useState('')
  const [routineAttempt, setRoutineAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getUserRoutine(userId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setRoutine(result)
          setRoutineError('')
        }
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) setRoutineError(requestError.message)
      })
    return () => controller.abort()
  }, [userId, routineRevision, routineAttempt])

  const estimatedDuration = routine?.days.some((day) => day.duration_minutes === null)
  const sessionMinutes = routine
    ? Math.max(...routine.days.map(getPlannedSessionMinutes)) : null

  useEffect(() => {
    const controller = new AbortController()
    getUserDays(userId, controller.signal)
      .then(getWeeklyProgress)
      .then((result) => {
        if (!controller.signal.aborted) setProgress(result)
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) setError(requestError.message)
      })
    return () => controller.abort()
  }, [userId, attempt])

  function retry() {
    setError('')
    setProgress(null)
    setAttempt((value) => value + 1)
  }

  return <aside className="training-panel">
    <div className="panel-label">{t('YOUR TRAINING')} <span className="tiny-pill">{t('THIS WEEK')}</span></div>
    <div className="training-card">
      <div className="card-topline"><span className="eyebrow">{t('BUILT AROUND YOU')}</span><Target size={18} /></div>
      <h3>{t('A little stronger.')}<br />{t('Every single week.')}</h3>
      <p>{t('Consistency is the goal.')}<br />{t("We'll take care of the plan.")}</p>
      <div className="barbell-art" aria-hidden="true">
        <svg viewBox="0 0 280 130" fill="none"><ellipse cx="140" cy="108" rx="98" ry="10" fill="#d6ded2" /><g transform="rotate(-17 140 65)"><rect x="27" y="61" width="226" height="12" rx="6" fill="#94a38b" /><rect x="50" y="30" width="23" height="74" rx="7" fill="#344c3b" /><rect x="73" y="39" width="15" height="56" rx="5" fill="#57745b" /><rect x="207" y="30" width="23" height="74" rx="7" fill="#344c3b" /><rect x="192" y="39" width="15" height="56" rx="5" fill="#57745b" /><path d="M57 38v58M214 38v58" stroke="#6f896f" strokeWidth="2" strokeLinecap="round" /></g><path d="m246 22 3 8 8 3-8 3-3 8-3-8-8-3 8-3Z" fill="#8eaa70" /><circle cx="37" cy="30" r="3" fill="#a9bc91" /></svg>
      </div>
      {routineError ? <div role="alert"><p>{t('Could not load routine: {{message}}', { message: routineError })}</p><button type="button" className="retry-button" onClick={() => { setRoutineError(''); setRoutine(undefined); setRoutineAttempt((value) => value + 1) }}>{t('Retry')}</button></div> :
        routine === undefined ? <p role="status">{t('Loading your routine…')}</p> :
          routine === null ? <p>{t('No saved routine yet')}</p> :
            <div className="training-stats"><div><strong>{routine.days.length} <span>{t('days')}</span></strong><small>{t('Weekly frequency')}</small></div><div title={estimatedDuration ? t('Estimated from planned sets: 5 min warm-up, 45 sec per set, 90 sec rest between sets, and 1 min between exercises. Recorded workouts are not used.') : undefined}><strong>{sessionMinutes} <span>{t('min')}</span></strong><small>{t(estimatedDuration ? 'Estimated max session' : 'Max session duration')}</small></div></div>}
      <button className="panel-routine-button" onClick={onOpen}>{t('Explore your routine')} <ArrowRight size={16} /></button>
    </div>
    <div className="week-card">
      <div><h4>{t('Your weekly rhythm')}</h4>{progress && <span>{t('trainingDaysLogged', { count: progress.completed })}</span>}</div>
      {error ? <div role="alert"><p>{t('Could not load weekly rhythm: {{message}}', { message: error })}</p><button type="button" className="retry-button" onClick={retry}>{t('Retry')}</button></div> :
        !progress ? <p role="status">{t('Loading weekly rhythm…')}</p> :
          <div className="week-days">{progress.weekDays.map(({ date, weekdayIndex, isTrainingDay }, index) =>
            <div key={date} data-date={date} title={date} aria-current={index === 6 ? 'date' : undefined}>
              <span>{t('weekDays', { returnObjects: true })[weekdayIndex]}</span>
              <span className={isTrainingDay ? 'training-day' : ''} aria-label={t(isTrainingDay ? 'Workout logged on {{date}}' : 'No workout logged on {{date}}', { date })}>{isTrainingDay ? <Dumbbell size={14} aria-hidden="true" /> : '–'}</span>
            </div>)}</div>}
      <p><span className="status-dot" />{t('Train. Recover. Repeat.')}</p>
    </div>
    <div className="coach-tip"><span className="tip-icon"><Sparkles size={18} /></span><div><h4>{t('Small steps. Real progress.')}</h4><p>{t('A good plan adapts to your life, not the other way around.')}</p><button onClick={() => onPrompt(t('How can I stay consistent with my training?'))}>{t("Let's talk about your goals")} <ArrowRight size={13} /></button></div></div>
    <div className="powered"><BrandMark small /><span>{t('One coach. A team of specialists.')}</span></div>
  </aside>
}
