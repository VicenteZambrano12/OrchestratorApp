/**
 * @file Compact conversation-level execution progress presentation.
 * SQL inspection events stay in WorkflowMonitor, while this list exposes public
 * stage labels. Active CSS animation follows pending state, not a simulated timer.
 */
import { Check, Circle, CircleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/**
 * Renders observed agent stages without inventing progress before events arrive.
 * @param {object} props - Execution status properties.
 * @param {Array<{id: string, label: string, kind?: string}>} [props.steps=[]] - Observed stages.
 * @param {boolean} [props.pending=false] - Marks the last visible stage as active.
 * @param {boolean} [props.failed=false] - Marks the final observed stage interrupted.
 * @returns {import('react').ReactElement|null} Stage list, connecting status, or no content.
 */
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
