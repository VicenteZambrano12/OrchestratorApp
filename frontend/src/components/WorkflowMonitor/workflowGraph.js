/**
 * @file Pure execution-trace adapter for the user-visible orchestrator system map.
 * A fixed full tree preserves architectural context while observed events determine
 * visited/active/failed highlights. SQL/source events are inspection metadata,
 * not a representation of private model reasoning.
 *
 * @typedef {object} WorkflowStep
 * @property {string} id - Stage identifier from the stream or synthesized playback.
 * @property {string} label - Public execution label.
 * @property {'sql'|'source'} [kind] - Optional inspection-node category.
 * @property {string} [parent] - Owning execution stage.
 * @property {string} [sql] - SQL template, without bound values/database rows.
 * @property {string} [source] - Database/source label.
 *
 * @typedef {object} WorkflowTrace
 * @property {string} [id] - Request identity used to reset playback.
 * @property {string} query - Submitted user prompt.
 * @property {WorkflowStep[]} steps - Observed execution stages.
 * @property {'idle'|'running'|'complete'|'failed'} status - Actual request status.
 * @property {string} error - Visible request error, if any.
 * @property {object} [response] - Most recent response snapshot.
 * @property {Array<{endpoint: string, data: object}>} [responses] - Response history for the inspector.
 */
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
  ['exercise_catalog', 'Searching the exercise catalog', 'exercise_explainer', 1, 3],
  ['exercise_sql', 'SQL query', 'exercise_catalog', 1, 4, 'sql'],
  ['exercise_explanation', 'Preparing an exercise explanation', 'exercise_catalog', 1, 6],
  ['past_day_exercise', 'Loading your last training day', 'past_routines_analyzer', 2, 3],
  ['compare_last_two_workouts', 'Comparing your last two workouts', 'past_routines_analyzer', 2, 4],
  ['weekly_performance', 'Reviewing your weekly performance', 'past_routines_analyzer', 2, 5],
  ['history_search', 'Searching your logged workout data', 'past_routines_analyzer', 2, 6],
  ['history_sql', 'SQL query', 'history_search', 2, 7, 'sql'],
  ['history_explanation', 'Summarizing your training results', 'history_search', 2, 9],
]

/**
 * Selects the fixed SQL/source branch for a streamed parent identifier.
 * @param {string} [parent] - Owning execution stage.
 * @returns {'routine'|'exercise'|'history'} Inspection branch prefix.
 */
function sqlGroup(parent) {
  if (parent?.startsWith('routine')) return 'routine'
  if (parent?.startsWith('exercise')) return 'exercise'
  return 'history'
}

/**
 * Maps dynamic progress IDs to stable nodes in the full architecture tree.
 * @param {WorkflowStep} step - Observed or synthesized event.
 * @returns {string} Fixed node ID, or the original stage ID.
 */
export function graphNodeId(step) {
  if (step.kind === 'sql') return `${sqlGroup(step.parent)}_sql`
  if (step.kind === 'source') return 'database'
  if (step.id.startsWith('exercise_explanation_')) return 'exercise_explanation'
  return step.id
}

/**
 * Expands observed stages into visual events with request and SQL-source nodes.
 * @param {WorkflowStep[]} steps - Actual execution events.
 * @param {WorkflowTrace['status']} status - Actual request status.
 * @returns {WorkflowStep[]} Ordered visual events; empty while idle.
 */
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

/**
 * Builds the full tree and overlays only the execution events revealed so far.
 * @param {WorkflowStep[]} events - Visible playback prefix.
 * @param {WorkflowTrace['status']} status - Visual playback status.
 * @returns {{nodes: Array<{id: string, label: string, parent?: string, kind?: string,
 * x: number, y: number, state: string, sql?: string, source?: string}>,
 * edges: Array<{id: string, from: string, to: string, state: string}>,
 * height: number, width: number}} Fixed geometry and observed node/connection states.
 */
export function buildWorkflowGraph(events, status) {
  /**
   * Positions a specialist column in the fixed graph.
   * @param {number} column - Zero-based column.
   * @returns {number} Horizontal coordinate.
   */
  const x = (column) => 25 + column * 330
  /**
   * Positions a stage row with consistent vertical spacing.
   * @param {number} row - Zero-based row.
   * @returns {number} Vertical coordinate.
   */
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
    { id: 'database', label: 'Database', kind: 'source', x: x(0), y: y(0) },
  ].map((node) => ({ ...node, state: 'idle' }))
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const visitedSources = new Set()
  let last = null
  let lastSource = null
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
    lastSource = event.kind === 'source' ? `${sqlGroup(event.parent)}_sql` : null
    if (lastSource) visitedSources.add(lastSource)
    if (!event.kind && id !== 'request') previousStage = id
    last = node
  }
  if (last && status === 'running') last.state = 'active'
  if (last && status === 'failed') last.state = 'failed'
  const edges = [
    ...nodes.filter(({ parent }) => parent).map((node) => ({
      id: node.id, from: node.parent, to: node.id, state: node.state,
    })),
    ...nodes.filter(({ kind }) => kind === 'sql').map((node) => ({
      id: `${node.id}-database`, from: node.id, to: 'database',
      state: visitedSources.has(node.id) ? node.id === lastSource ? byId.get('database').state : 'done' : 'idle',
    })),
  ]
  return { nodes, edges, height: 1160, width: 1340 }
}

/**
 * Fits the entire fixed tree inside the measured viewport without cropping.
 * @param {{width: number, height: number}} size - Available viewport dimensions.
 * @param {{width: number, height: number}} graph - Fixed tree dimensions.
 * @returns {number} Non-negative uniform scale; zero until viewport measurement.
 */
export function fitWorkflowGraph(size, graph) {
  return Math.max(0, Math.min(size.width / graph.width, size.height / graph.height))
}
