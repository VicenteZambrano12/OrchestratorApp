export const branches = [
  { id: 'routine_maker', label: 'Routine maker' },
  { id: 'exercise_explainer', label: 'Exercise explainer' },
  { id: 'past_routines_analyzer', label: 'Progress analyzer' },
  { id: 'general_guidance', label: 'General guidance' },
]

const stages = [
  ['routine_context', 'Loading your routine and exercise data', 'routine_maker', 0, 3],
  ['routine_routing', 'Choosing the next routine action', 'routine_context', 0, 4],
  ['routine_build', 'Building your routine preview', 'routine_routing', 0, 5],
  ['routine_updater', 'Updating your routine preview', 'routine_routing', 0, 6],
  ['routine_save', 'Saving your confirmed routine', 'routine_routing', 0, 7],
  ['routine_sql', 'SQL query', 'routine_context', 0, 8, 'sql'],
  ['routine_source', 'Database source', 'routine_sql', 0, 9, 'source'],
  ['exercise_catalog', 'Searching the exercise catalog', 'exercise_explainer', 1, 3],
  ['exercise_sql', 'SQL query', 'exercise_catalog', 1, 4, 'sql'],
  ['exercise_source', 'Database source', 'exercise_sql', 1, 5, 'source'],
  ['exercise_explanation', 'Preparing an exercise explanation', 'exercise_catalog', 1, 6],
  ['past_day_exercise', 'Loading your last training day', 'past_routines_analyzer', 2, 3],
  ['compare_last_two_workouts', 'Comparing your last two workouts', 'past_routines_analyzer', 2, 4],
  ['weekly_performance', 'Reviewing your weekly performance', 'past_routines_analyzer', 2, 5],
  ['history_search', 'Searching your logged workout data', 'past_routines_analyzer', 2, 6],
  ['history_sql', 'SQL query', 'history_search', 2, 7, 'sql'],
  ['history_source', 'Database source', 'history_sql', 2, 8, 'source'],
  ['history_explanation', 'Summarizing your training results', 'history_search', 2, 9],
]

function sqlGroup(parent) {
  if (parent?.startsWith('routine')) return 'routine'
  if (parent?.startsWith('exercise')) return 'exercise'
  return 'history'
}

export function graphNodeId(step) {
  if (step.kind === 'sql') return `${sqlGroup(step.parent)}_sql`
  if (step.kind === 'source') return `${sqlGroup(step.parent)}_source`
  if (step.id.startsWith('exercise_explanation_')) return 'exercise_explanation'
  return step.id
}

export function playbackEvents(steps, status) {
  if (status === 'idle') return []
  return [
    { id: 'request', label: 'User request' },
    ...steps.flatMap((step) => step.kind === 'sql' ? [
      step,
      { id: `${step.id}_source`, label: step.source, kind: 'source', parent: step.parent, source: step.source },
    ] : [step]),
  ]
}

export function buildWorkflowGraph(events, status) {
  const x = (column) => 25 + column * 330
  const y = (row) => 20 + row * 104
  const nodes = [
    { id: 'request', label: 'User request', x: 520, y: y(0) },
    { id: 'orchestrator', label: 'Analyzing your request', parent: 'request', x: 520, y: y(1) },
    ...branches.map((branch, index) => ({
      ...branch, parent: 'orchestrator', x: x(index), y: y(2),
    })),
    ...stages.map(([id, label, parent, column, row, kind]) => ({
      id, label, parent, kind, x: x(column), y: y(row),
    })),
    { id: 'response', label: 'Your response is ready', parent: 'orchestrator', x: 520, y: y(10) },
  ].map((node) => ({ ...node, state: 'idle' }))
  const byId = new Map(nodes.map((node) => [node.id, node]))
  let last = null
  let previousStage = 'orchestrator'
  for (const event of events) {
    const id = graphNodeId(event)
    const node = byId.get(id)
    if (!node) continue
    if (id === 'response') node.parent = previousStage
    else if (event.kind === 'sql' && byId.has(event.parent)) node.parent = event.parent
    if (id === 'history_search' && ['past_day_exercise', 'compare_last_two_workouts', 'weekly_performance'].includes(previousStage)) node.parent = previousStage
    node.state = 'done'
    node.sql = event.sql
    node.source = event.source
    if (event.kind === 'source') node.label = event.source
    if (!event.kind && id !== 'request') previousStage = id
    last = node
  }
  if (last && status === 'running') last.state = 'active'
  if (last && status === 'failed') last.state = 'failed'
  return { nodes, height: 1160, width: 1340 }
}

export function fitWorkflowGraph(size, graph) {
  return Math.max(0, Math.min(size.width / graph.width, size.height / graph.height))
}
