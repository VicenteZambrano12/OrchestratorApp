/** @file Reusable navigation card distinguishing illustrative and live plan previews. */
import { ArrowRight, Dumbbell } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getPlanSummary } from '../../features/RoutinePreview/plan-summary/getPlanSummary'

/**
 * Renders translated summary copy without loading or saving routine content.
 * @param {object} props - Preview link properties.
 * @param {() => void} props.onOpen - Parent-owned plan navigation action.
 * @param {boolean} props.demo - Selects explicitly illustrative summary copy.
 * @returns {import('react').ReactElement} Plan-opening button.
 */
export default function RoutinePreview({ onOpen, demo }) {
  const { t } = useTranslation()
  const { title, description } = getPlanSummary(demo)
  return <button className="routine-preview" onClick={onOpen}>
    <span className="preview-icon"><Dumbbell size={22} /></span>
    <span><strong>{t(title)}</strong><span>{t(description)}</span></span>
    <span className="preview-action">{t('View plan')} <ArrowRight size={16} /></span>
  </button>
}
