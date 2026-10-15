import { ArrowRight, BarChart3, Gauge, Layers, Repeat, Scale, TrendingDown, TrendingUp } from 'lucide-react'
import { compareWorkouts, formatDate, weightUnit } from '../../features/PastRoutinesReport/report-data/reportData'
import { useReportFormat } from '../../features/PastRoutinesReport/report-data/useReportFormat'
import { Delta, KpiStrip, MuscleChip, ReportSection } from './ReportParts'

function SessionCard({ label, session, latest }) {
  const { language } = useReportFormat()
  return <div className={latest ? 'compare-session latest' : 'compare-session'}>
    <span>{label}</span>
    <strong>{session.date ? formatDate(session.date, language) : '—'}</strong>
    <small>{session.day || ''}</small>
  </div>
}

function ChangeList({ title, icon: Icon, items, tone, empty }) {
  const { number } = useReportFormat()
  return <div className={`change-list ${tone}`}>
    <h5><Icon size={14} />{title}</h5>
    {items.length ? <ul>
      {items.map((exercise) => <li key={exercise.name}>
        <span>{exercise.name}</span>
        <b>{exercise.change > 0 ? '+' : '−'}{number(Math.abs(exercise.change * 100))}%</b>
      </li>)}
    </ul> : <p>{empty}</p>}
  </div>
}

export default function CompareView({ rows }) {
  const { t, number, weight } = useReportFormat()
  const unit = weightUnit(rows)
  const { latest, previous, exercises, strengths, weaknesses } = compareWorkouts(rows)
  const changed = exercises.filter((exercise) => exercise.change !== null)
  const maxChange = Math.max(0.01, ...changed.map((exercise) => Math.abs(exercise.change)))
  const scoreLabel = (exercise, stats) => (exercise.bodyweight ? `${number(stats.score)} ${t('reps')}` : `${number(stats.score)} ${unit}`)
  return <>
    <div className="compare-sessions">
      <SessionCard label={t('Previous')} session={previous} />
      <ArrowRight size={18} aria-hidden="true" />
      <SessionCard label={t('Latest')} session={latest} latest />
    </div>
    {previous.sets === 0 && <p className="report-note">{t('Only one matching workout was found, so there is nothing to compare yet.')}</p>}
    <KpiStrip items={[
      { icon: Layers, label: t('Sets'), value: number(latest.sets), delta: <Delta value={latest.sets - previous.sets} /> },
      { icon: Repeat, label: t('Reps'), value: number(latest.reps), delta: <Delta value={latest.reps - previous.reps} /> },
      { icon: BarChart3, label: t('Volume'), value: `${number(latest.volume)} ${unit}`, delta: <Delta value={latest.volume - previous.volume} suffix={` ${unit}`} /> },
      { icon: Gauge, label: t('Avg RPE'), value: latest.avgRpe === null ? '—' : number(latest.avgRpe, 1), delta: latest.avgRpe !== null && previous.avgRpe !== null ? <Delta value={latest.avgRpe - previous.avgRpe} digits={1} inverse /> : null },
    ]} />
    {changed.length > 0 && <ReportSection title={t('Strengths & weaknesses')} icon={Scale}
      aside={<span className="report-hint">{t('Change in volume (reps for bodyweight)')}</span>}>
      <ul className="diverging-chart">
        {changed.map((exercise) => {
          const width = (Math.abs(exercise.change) / maxChange) * 50
          const tone = exercise.change > 0 ? 'up' : exercise.change < 0 ? 'down' : 'flat'
          return <li key={exercise.name} className={tone}>
            <span className="diverging-label">{exercise.name}</span>
            <span className="diverging-track">
              <span className="diverging-bar" style={{ width: `${Math.max(width, 1)}%`, [exercise.change >= 0 ? 'left' : 'right']: '50%' }} />
            </span>
            <span className="diverging-value">{exercise.change > 0 ? '+' : exercise.change < 0 ? '−' : '±'}{number(Math.abs(exercise.change * 100))}%</span>
          </li>
        })}
      </ul>
      <div className="change-lists">
        <ChangeList title={t('Strengths')} icon={TrendingUp} items={strengths.slice(0, 3)} tone="up" empty={t('No improvements this time.')} />
        <ChangeList title={t('Weaknesses')} icon={TrendingDown} items={weaknesses.slice(0, 3)} tone="down" empty={t('Nothing went backwards. Nice work!')} />
      </div>
    </ReportSection>}
    <ReportSection title={t('Latest vs previous')} icon={BarChart3}
      aside={<span className="report-legend-inline"><i className="previous" />{t('Previous')}<i className="latest" />{t('Latest')}</span>}>
      <ul className="paired-chart">
        {exercises.map((exercise) => {
          const max = Math.max(1, exercise.latest?.score || 0, exercise.previous?.score || 0)
          return <li key={exercise.name}>
            <div className="paired-head">
              <span>{exercise.name}</span><MuscleChip muscle={exercise.muscle} />
              <small>{exercise.previous ? weight(exercise.previous.bestWeight, unit) : '—'} → {exercise.latest ? weight(exercise.latest.bestWeight, unit) : '—'}</small>
            </div>
            {['previous', 'latest'].map((key) => <div key={key} className={`paired-row ${key}`}>
              <span className="paired-track"><span style={{ width: `${exercise[key] ? (exercise[key].score / max) * 100 : 0}%` }} /></span>
              <span className="paired-value">{exercise[key] ? scoreLabel(exercise, exercise[key]) : t('Not done')}</span>
            </div>)}
          </li>
        })}
      </ul>
    </ReportSection>
  </>
}
