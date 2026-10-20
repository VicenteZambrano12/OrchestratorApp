/**
 * @file Structured history-response router pairing agent Markdown with measured
 * workout visualizations. Receives a validated analysis envelope from the chat
 * boundary; an empty result is a valid no-history state, not a pipeline failure.
 */
import ReactMarkdown from 'react-markdown'
import { CalendarDays, GitCompareArrows, Radar, SearchX } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '../../features/PastRoutinesReport/report-data/reportData'
import PastDayView from './PastDayView'
import CompareView from './CompareView'
import WeeklyView from './WeeklyView'
import './PastRoutinesReport.css'

const ROUTE_VIEWS = {
  past_day_exercise: { icon: CalendarDays, label: 'Past workout', View: PastDayView },
  compare_last_two_workouts: { icon: GitCompareArrows, label: 'Workout comparison', View: CompareView },
  weekly_performance: { icon: Radar, label: 'Weekly performance', View: WeeklyView },
}

/**
 * Builds a route-specific title without inventing missing session identity.
 * @param {import('../../features/PastRoutinesReport/report-data/reportData').PastRoutinesAnalysis} analysis - Validated envelope.
 * @param {import('i18next').TFunction} t - Current translator.
 * @param {string} language - Date formatting locale.
 * @returns {string} Localized report heading.
 */
function reportTitle(analysis, t, language) {
  const first = analysis.data[0]
  if (analysis.route === 'weekly_performance') return t('Your last 7 days')
  if (analysis.route === 'compare_last_two_workouts') return first?.training_day || t('Your last two workouts')
  if (!first) return t('Your last workout')
  return [first.training_day, formatDate(first.training_date, language, { weekday: 'long', day: 'numeric', month: 'long' })].filter(Boolean).join(' · ')
}

/**
 * Chooses the validated history route's view and explicit empty-result presentation.
 * @param {object} props - Report properties.
 * @param {import('../../features/PastRoutinesReport/report-data/reportData').PastRoutinesAnalysis} props.analysis - Validated specialist result.
 * @returns {import('react').ReactElement} Agent explanation and route-specific report body.
 */
export default function PastRoutinesReport({ analysis }) {
  const { t, i18n } = useTranslation()
  const { icon: Icon, label, View } = ROUTE_VIEWS[analysis.route]
  const hasData = analysis.data.length > 0
  return <section className="routines-report" aria-label={t(label)}>
    <header className="report-header">
      <span className="report-icon"><Icon size={20} /></span>
      <div>
        <span className="report-eyebrow">{t(label)}{analysis.day_type && <em>{analysis.day_type}</em>}</span>
        <h3>{reportTitle(analysis, t, i18n.resolvedLanguage || 'en')}</h3>
      </div>
    </header>
    <div className="report-explain markdown-response"><ReactMarkdown>{analysis.llm_explain}</ReactMarkdown></div>
    <div className="report-body">
      {hasData ? <View rows={analysis.data} /> : <div className="report-empty"><SearchX size={22} /><p>{t('No logged workouts matched this request yet.')}</p></div>}
    </div>
  </section>
}
