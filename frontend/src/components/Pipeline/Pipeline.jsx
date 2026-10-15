import { Check, Circle, CircleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export default function Pipeline({ steps = [], pending = false, failed = false }) {
  const { t } = useTranslation()
  steps = steps.filter((step) => step.kind !== 'sql')
  if (!steps.length) return pending ? <p className="pipeline-waiting" role="status">{t('Connecting to your coach')}</p> : null
  return (
    <ol className={`pipeline pipeline-steps ${pending ? 'is-pending' : ''}`} aria-label={t('Request steps')}>
      {steps.map(({ id, label }, index) => {
        const active = pending && index === steps.length - 1
        const interrupted = failed && index === steps.length - 1
        const Icon = interrupted ? CircleAlert : failed ? Circle : Check
        return <li className={`pipeline-stage${active ? ' is-active' : ''}`} key={id}>
          <span className="stage-icon" aria-hidden="true">{active ? <span className="loading-ring" /> : <Icon size={14} />}</span>
          <span>{t(label)}</span>
          {(active || interrupted) && <span className="sr-only">{t(active ? 'In progress' : 'Interrupted')}</span>}
        </li>
      })}
    </ol>
  )
}
