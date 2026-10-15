import { useTranslation } from 'react-i18next'
import { MUSCLE_COLORS, muscleLabel } from '../../features/PastRoutinesReport/report-data/reportData'
import { useReportFormat } from '../../features/PastRoutinesReport/report-data/useReportFormat'

export function MuscleChip({ muscle }) {
  const { t } = useTranslation()
  if (!muscle) return null
  return <span className="report-muscle" style={{ '--muscle-color': MUSCLE_COLORS[muscle] || 'var(--text-muted)' }}>{t(muscleLabel(muscle))}</span>
}

export function KpiStrip({ items }) {
  return <div className="report-kpis">
    {items.map(({ icon: Icon, label, value, delta }) => <div key={label} className="report-kpi">
      <span className="report-kpi-label">{Icon && <Icon size={13} />}{label}</span>
      <strong>{value}</strong>
      {delta}
    </div>)}
  </div>
}

export function ReportSection({ title, icon: Icon, children, aside }) {
  return <section className="report-section">
    <header><h4>{Icon && <Icon size={14} />}{title}</h4>{aside}</header>
    {children}
  </section>
}

export function Delta({ value, digits = 0, suffix = '', inverse = false }) {
  const { number } = useReportFormat()
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const rounded = Number(value.toFixed(digits))
  const tone = rounded === 0 ? 'flat' : (rounded > 0) !== inverse ? 'up' : 'down'
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : '±'
  return <span className={`report-delta ${tone}`}>{sign}{number(Math.abs(rounded), digits)}{suffix}</span>
}
