import { ArrowRight, Dumbbell } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getPlanSummary } from '../../features/RoutinePreview/plan-summary/getPlanSummary'

export default function RoutinePreview({ onOpen, demo }) {
  const { t } = useTranslation()
  const { title, description } = getPlanSummary(demo)
  return <button className="routine-preview" onClick={onOpen}>
    <span className="preview-icon"><Dumbbell size={22} /></span>
    <span><strong>{t(title)}</strong><span>{t(description)}</span></span>
    <span className="preview-action">{t('View plan')} <ArrowRight size={16} /></span>
  </button>
}
