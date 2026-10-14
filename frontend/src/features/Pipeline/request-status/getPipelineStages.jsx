import { CheckCheck, Dumbbell, Layers3 } from 'lucide-react'
import { subsystemNames } from '../../ai-chat/api/chat'

export function getPipelineStages(subsystem, pending) {
  return [
    { name: 'Orchestrator', detail: pending ? 'Routing your request' : 'Matched your request to the right specialist', icon: Layers3 },
    { name: subsystemNames[subsystem] || 'Specialist', detail: pending ? 'Waiting for the response' : 'Returned a response for your review', icon: Dumbbell },
    { name: 'Response', detail: pending ? 'Waiting for the response' : 'Ready to review', icon: CheckCheck },
  ]
}
