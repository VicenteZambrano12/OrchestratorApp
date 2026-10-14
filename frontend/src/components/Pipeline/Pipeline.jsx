import { Check, ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usePipelineExpansion } from '../../features/Pipeline/expansion/usePipelineExpansion'
import { getPipelineStages } from '../../features/Pipeline/request-status/getPipelineStages'

export default function Pipeline({ subsystem, pending = false, demo = true }) {
  const { t } = useTranslation()
  const { expanded, toggleExpansion } = usePipelineExpansion()
  const stages = getPipelineStages(subsystem, pending)
  return (
    <div className={`pipeline ${pending ? 'is-pending' : ''}`}>
      <button className="pipeline-toggle" onClick={toggleExpansion} aria-expanded={expanded}>
        <span><span className={pending ? 'status-dot pulsing' : 'status-dot'} />{t(pending ? 'Working on your request' : 'Your coaching team, in sync')}</span>
        <span className="pipeline-meta">{t(demo ? 'Demo pipeline' : 'Request status')}<ChevronDown size={14} className={expanded ? 'rotated' : ''} /></span>
      </button>
      {expanded && <div className="pipeline-stages">{stages.map(({ name, detail, icon: Icon }, index) => (
        <div className="pipeline-stage" key={name}>
          <span className="stage-icon"><Icon size={15} /></span>
          <div><strong>{t(name)}</strong><p>{t(detail)}</p></div>
          {!pending && <Check size={14} className="stage-check" />}
          {pending && index === 0 && <span className="loading-ring" />}
        </div>
      ))}<p className="pipeline-disclaimer">{t(demo ? 'Illustrative steps for this mockup.' : 'The API returns a final result, not live intermediate steps.')}</p></div>}
    </div>
  )
}
