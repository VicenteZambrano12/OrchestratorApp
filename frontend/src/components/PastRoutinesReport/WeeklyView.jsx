import { BarChart3, CalendarDays, Dumbbell, Layers, Medal, Radar, Target, Trophy } from 'lucide-react'
import { MUSCLE_COLORS, bestExercises, dailyVolume, formatDate, muscleLabel, summarize, weeklyMuscles, weightUnit } from '../../features/PastRoutinesReport/report-data/reportData'
import { useReportFormat } from '../../features/PastRoutinesReport/report-data/useReportFormat'
import { KpiStrip, MuscleChip, ReportSection } from './ReportParts'
import RadarChart from './RadarChart'

export default function WeeklyView({ rows }) {
  const { t, language, number, weight } = useReportFormat()
  const unit = weightUnit(rows)
  const totals = summarize(rows)
  const muscles = weeklyMuscles(rows)
  const days = dailyVolume(rows)
  const best = bestExercises(rows)
  const heaviest = [...best].sort((a, b) => b.bestWeight - a.bestWeight)[0]
  const maxSets = Math.max(1, ...muscles.map((muscle) => muscle.sets))
  const maxVolume = Math.max(1, ...muscles.map((muscle) => muscle.volume))
  const maxDay = Math.max(1, ...days.map((day) => day.volume))
  const trained = muscles.filter((muscle) => muscle.sets > 0)
  const missed = muscles.filter((muscle) => muscle.sets === 0)
  const series = [{ name: t('Sets'), color: 'var(--accent-primary)' }, { name: t('Volume'), color: '#6366f1' }]
  const axes = muscles.map((muscle) => ({
    label: t(muscleLabel(muscle.muscle)),
    active: muscle.sets > 0,
    values: [muscle.sets / maxSets, muscle.volume / maxVolume],
    tooltips: [t('reportSets', { count: muscle.sets }), `${number(muscle.volume)} ${unit}`],
  }))
  return <>
    <KpiStrip items={[
      { icon: CalendarDays, label: t('Training days'), value: number(days.length) },
      { icon: Layers, label: t('Sets'), value: number(totals.sets) },
      { icon: BarChart3, label: t('Volume'), value: `${number(totals.volume)} ${unit}` },
      { icon: Target, label: t('Muscles hit'), value: `${trained.length}/${muscles.length}` },
    ]} />
    <ReportSection title={t('Muscle balance')} icon={Radar}
      aside={<span className="report-legend-inline"><i className="latest" />{t('Sets')}<i className="volume" />{t('Volume')}</span>}>
      <div className="radar-layout">
        <RadarChart axes={axes} series={series} label={t('Weekly sets and volume by muscle group')} />
        <ul className="muscle-ranking">
          {[...trained].sort((a, b) => b.sets - a.sets).map((muscle) => <li key={muscle.muscle} style={{ '--muscle-color': MUSCLE_COLORS[muscle.muscle] || 'var(--accent-primary)' }}>
            <span>{t(muscleLabel(muscle.muscle))}</span>
            <span className="muscle-ranking-bar"><span style={{ width: `${(muscle.sets / maxSets) * 100}%` }} /></span>
            <b>{muscle.sets}</b>
          </li>)}
          {missed.length > 0 && <li className="muscle-missed">{t('Not trained')}: {missed.map((muscle) => t(muscleLabel(muscle.muscle))).join(', ')}</li>}
        </ul>
      </div>
    </ReportSection>
    {heaviest && <div className="best-lift">
      <Trophy size={26} />
      <div>
        <span>{t('Heaviest lift of the week')}</span>
        <strong>{heaviest.name}</strong>
        <MuscleChip muscle={heaviest.muscle} />
      </div>
      <b>{weight(heaviest.bestWeight, unit)}<small>× {heaviest.reps} {t('reps')}</small></b>
    </div>}
    <ReportSection title={t('Best exercises')} icon={Medal} aside={<span className="report-hint">{t('Ranked by estimated 1RM')}</span>}>
      <ol className="podium">
        {best.map((exercise, index) => <li key={exercise.name} className={`rank-${index + 1}`}>
          <span className="podium-rank">{index + 1}</span>
          <div><strong>{exercise.name}</strong><MuscleChip muscle={exercise.muscle} /></div>
          <span className="podium-stat"><small>{t('Best set')}</small>{weight(exercise.bestWeight, unit)} × {exercise.reps}</span>
          <span className="podium-stat"><small>{t('Est. 1RM')}</small>{exercise.e1rm > 0 ? `${number(exercise.e1rm, 1)} ${unit}` : '—'}</span>
        </li>)}
      </ol>
    </ReportSection>
    <ReportSection title={t('Daily volume')} icon={Dumbbell}>
      <div className="column-chart">
        {days.map((day) => <div key={day.date} className="column" title={`${day.day || ''} · ${number(day.volume)} ${unit}`}>
          <span className="column-value">{number(day.volume)}</span>
          <span className="column-bar"><span style={{ height: `${Math.max(4, (day.volume / maxDay) * 100)}%` }} /></span>
          <span className="column-label">{formatDate(day.date, language, { weekday: 'short', day: 'numeric' })}</span>
          <small className="column-sub">{day.day || ''}</small>
        </div>)}
      </div>
    </ReportSection>
  </>
}
