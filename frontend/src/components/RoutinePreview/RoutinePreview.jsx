import { ArrowRight, Dumbbell } from 'lucide-react'
import { getPlanSummary } from '../../features/RoutinePreview/plan-summary/getPlanSummary'

export default function RoutinePreview({ onOpen, demo }) {
  const { title, description } = getPlanSummary(demo)
  return <button className="routine-preview" onClick={onOpen}>
    <span className="preview-icon"><Dumbbell size={22} /></span>
    <span><strong>{title}</strong><span>{description}</span></span>
    <span className="preview-action">View plan <ArrowRight size={16} /></span>
  </button>
}
