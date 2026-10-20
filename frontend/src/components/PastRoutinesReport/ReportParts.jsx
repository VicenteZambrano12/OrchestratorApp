/**
 * @file Shared presentation primitives for workout-history reports.
 * Locale formatting and semantic tones are centralized; callers supply measured
 * statistics and translated labels rather than triggering data requests here.
 */
import { useTranslation } from 'react-i18next'
import { MUSCLE_COLORS, muscleLabel } from '../../features/PastRoutinesReport/report-data/reportData'
import { useReportFormat } from '../../features/PastRoutinesReport/report-data/useReportFormat'

/**
 * Labels a known muscle with its semantic color.
 * @param {object} props - Chip properties.
 * @param {string|null} props.muscle - Muscle identifier; absent values hide the chip.
 * @returns {import('react').ReactElement|null} Translated muscle chip or null.
 */
export function MuscleChip({ muscle }) {
  const { t } = useTranslation()
  if (!muscle) return null
  return <span className="report-muscle" style={{ '--muscle-color': MUSCLE_COLORS[muscle] || 'var(--text-muted)' }}>{t(muscleLabel(muscle))}</span>
}

/**
 * Lays out already-formatted report metrics and optional change indicators.
 * @param {object} props - Metric strip properties.
 * @param {Array<{icon?: import('lucide-react').LucideIcon, label: string,
 * value: import('react').ReactNode, delta?: import('react').ReactNode}>} props.items - Display metrics.
 * @returns {import('react').ReactElement} KPI collection.
 */
export function KpiStrip({ items }) {
  return <div className="report-kpis">
    {items.map(({ icon: Icon, label, value, delta }) => <div key={label} className="report-kpi">
      <span className="report-kpi-label">{Icon && <Icon size={13} />}{label}</span>
      <strong>{value}</strong>
      {delta}
    </div>)}
  </div>
}

/**
 * Provides consistent section structure for report charts and tables.
 * @param {object} props - Section properties.
 * @param {string} props.title - Translated heading.
 * @param {import('lucide-react').LucideIcon} [props.icon] - Heading symbol.
 * @param {import('react').ReactNode} props.children - Section body.
 * @param {import('react').ReactNode} [props.aside] - Heading-side legend or explanation.
 * @returns {import('react').ReactElement} Report section with optional legend.
 */
export function ReportSection({ title, icon: Icon, children, aside }) {
  return <section className="report-section">
    <header><h4>{Icon && <Icon size={14} />}{title}</h4>{aside}</header>
    {children}
  </section>
}

/**
 * Formats a finite signed delta with context-dependent improvement coloring.
 * @param {object} props - Delta properties.
 * @param {number|null|undefined} props.value - Measured change; non-finite values hide it.
 * @param {number} [props.digits=0] - Rounding/format precision.
 * @param {string} [props.suffix=''] - Already-formatted unit suffix.
 * @param {boolean} [props.inverse=false] - Treats smaller values as improvement, e.g. RPE.
 * @returns {import('react').ReactElement|null} Semantic delta label or no measurement.
 */
export function Delta({ value, digits = 0, suffix = '', inverse = false }) {
  const { number } = useReportFormat()
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const rounded = Number(value.toFixed(digits))
  const tone = rounded === 0 ? 'flat' : (rounded > 0) !== inverse ? 'up' : 'down'
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : '±'
  return <span className={`report-delta ${tone}`}>{sign}{number(Math.abs(rounded), digits)}{suffix}</span>
}
