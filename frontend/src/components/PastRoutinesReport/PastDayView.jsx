/**
 * @file Last-workout report view deriving set-level and muscle-level visualizations.
 * All statistics come from provided backend history rows; this module does not
 * fetch data or infer missing exertion measurements.
 */
import { BarChart3, Dumbbell, Flame, Gauge, Layers, ListChecks, Repeat } from 'lucide-react'
import { MUSCLE_COLORS, groupExercises, muscleDistribution, muscleLabel, rpeTone, summarize, weightUnit } from '../../features/PastRoutinesReport/report-data/reportData'
import { useReportFormat } from '../../features/PastRoutinesReport/report-data/useReportFormat'
import { KpiStrip, MuscleChip, ReportSection } from './ReportParts'

/**
 * Renders a performed set with a relative-load indicator and optional RPE.
 * @param {object} props - Set row properties.
 * @param {import('../../features/PastRoutinesReport/report-data/reportData').ReportRow} props.row - Backend set measurements.
 * @param {number} props.maxLoad - Exercise-local normalization maximum.
 * @param {string} props.unit - Display load unit.
 * @param {boolean} props.bodyweight - Uses reps instead of external load for bar width.
 * @returns {import('react').ReactElement} Set measurements with semantic intensity.
 */
function SetRow({ row, maxLoad, unit, bodyweight }) {
  const { t, number, weight } = useReportFormat()
  const load = bodyweight ? row.reps || 0 : row.weight || 0
  const width = maxLoad > 0 ? Math.max(6, (load / maxLoad) * 100) : 0
  return <li className="set-row">
    <span className="set-number">{row.set_number ?? '–'}</span>
    <span className="set-main">
      <strong>{row.reps ?? '–'}</strong><small>{t('reps')}</small>
      <span className="set-times">×</span>
      <strong>{weight(row.weight || 0, unit)}</strong>
    </span>
    <span className="set-load" aria-hidden="true"><span style={{ width: `${width}%` }} /></span>
    <span className={`set-rpe ${rpeTone(row.rpe)}`} title={t('Rate of perceived exertion')}>
      {typeof row.rpe === 'number' ? `RPE ${number(row.rpe, 1)}` : '—'}
    </span>
  </li>
}

/**
 * Displays ordered sets and aggregate measurements for one exercise.
 * @param {object} props - Exercise section properties.
 * @param {import('../../features/PastRoutinesReport/report-data/reportData').ExerciseGroup} props.exercise - Grouped set statistics.
 * @param {number} props.index - Zero-based display position.
 * @param {string} props.unit - Load unit.
 * @returns {import('react').ReactElement} Exercise header and performed-set list.
 */
function ExerciseBlock({ exercise, index, unit }) {
  const { t, number, weight } = useReportFormat()
  const maxLoad = Math.max(0, ...exercise.sets.map((row) => (exercise.bodyweight ? row.reps || 0 : row.weight || 0)))
  return <article className="exercise-block" style={{ '--muscle-color': MUSCLE_COLORS[exercise.muscle] || 'var(--accent-primary)' }}>
    <header>
      <span className="exercise-index">{index + 1}</span>
      <div><h5>{exercise.name}</h5><MuscleChip muscle={exercise.muscle} /></div>
      <dl>
        <div><dt>{t('Top set')}</dt><dd>{weight(exercise.bestWeight, unit)}</dd></div>
        <div><dt>{exercise.bodyweight ? t('Reps') : t('Volume')}</dt><dd>{exercise.bodyweight ? number(exercise.reps) : `${number(exercise.volume)} ${unit}`}</dd></div>
      </dl>
    </header>
    <ol className="set-list">
      {exercise.sets.map((row, setIndex) => <SetRow key={`${row.set_number}-${setIndex}`} row={row} maxLoad={maxLoad} unit={unit} bodyweight={exercise.bodyweight} />)}
    </ol>
  </article>
}

/**
 * Builds a single-workout report using locale-bound formatting.
 * @param {object} props - Report properties.
 * @param {import('../../features/PastRoutinesReport/report-data/reportData').ReportRow[]} props.rows - Performed-set data.
 * @returns {import('react').ReactElement} KPIs, muscle split, exercises, and measured-volume chart.
 */
export default function PastDayView({ rows }) {
  const { t, number } = useReportFormat()
  const unit = weightUnit(rows)
  const totals = summarize(rows)
  const exercises = groupExercises(rows)
  const split = muscleDistribution(rows)
  const maxVolume = Math.max(0, ...exercises.map((exercise) => exercise.volume))
  return <>
    <KpiStrip items={[
      { icon: Dumbbell, label: t('Exercises'), value: number(totals.exercises) },
      { icon: Layers, label: t('Sets'), value: number(totals.sets) },
      { icon: Repeat, label: t('Reps'), value: number(totals.reps) },
      { icon: BarChart3, label: t('Volume'), value: `${number(totals.volume)} ${unit}` },
      { icon: Gauge, label: t('Avg RPE'), value: totals.avgRpe === null ? '—' : number(totals.avgRpe, 1) },
    ]} />
    <ReportSection title={t('Muscle split')} icon={Flame}>
      <div className="muscle-split" role="img" aria-label={split.map((item) => `${t(muscleLabel(item.muscle))} ${Math.round(item.share * 100)}%`).join(', ')}>
        {split.map((item) => <span key={item.muscle} style={{ flexGrow: item.sets, background: MUSCLE_COLORS[item.muscle] || 'var(--text-muted)' }} />)}
      </div>
      <ul className="report-legend">
        {split.map((item) => <li key={item.muscle} style={{ '--muscle-color': MUSCLE_COLORS[item.muscle] || 'var(--text-muted)' }}>
          {t(muscleLabel(item.muscle))}<b>{t('reportSets', { count: item.sets })}</b>
        </li>)}
      </ul>
    </ReportSection>
    <ReportSection title={t('Exercise breakdown')} icon={ListChecks}>
      <div className="exercise-blocks">
        {exercises.map((exercise, index) => <ExerciseBlock key={`${exercise.name}-${index}`} exercise={exercise} index={index} unit={unit} />)}
      </div>
    </ReportSection>
    {maxVolume > 0 && <ReportSection title={t('Volume by exercise')} icon={BarChart3}>
      <ul className="hbar-chart">
        {exercises.filter((exercise) => exercise.volume > 0).map((exercise, index) => <li key={`${exercise.name}-${index}`}>
          <span className="hbar-label">{exercise.name}</span>
          <span className="hbar-track"><span style={{ width: `${(exercise.volume / maxVolume) * 100}%`, background: MUSCLE_COLORS[exercise.muscle] || 'var(--accent-primary)' }} /></span>
          <span className="hbar-value">{number(exercise.volume)} {unit}</span>
        </li>)}
      </ul>
    </ReportSection>}
  </>
}
