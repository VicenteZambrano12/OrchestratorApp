/**
 * @file Regression tests for orchestrator graph mapping, fragmented NDJSON, and
 * the live-monitor popup lifecycle. Browser state is isolated with happy-dom;
 * mocked transport verifies progress visualization never delays the API result.
 */
import assert from 'node:assert/strict'
import { after, before, mock, test } from 'node:test'
import { act, createElement } from 'react'
import { Window } from 'happy-dom'
import { createServer } from 'vite'
import { buildWorkflowGraph, branches, fitWorkflowGraph, playbackEvents } from './workflowGraph.js'
import { readChatStream } from '../../features/ai-chat/api/readChatStream.js'

const steps = [
  { id: 'orchestrator', label: 'Analyzing your request' },
  { id: 'exercise_explainer', label: 'Identifying the exercises to explain' },
  { id: 'exercise_catalog', label: 'Searching the exercise catalog' },
  { id: 'sql_1', label: 'Executing SQL query', kind: 'sql', parent: 'exercise_catalog', sql: 'SELECT * FROM dim_exercises WHERE id = ?', source: 'SQLite / gym_app.db' },
]

test('graph highlights only the executed branch and its connection to the shared database', () => {
  const events = playbackEvents(steps, 'running')
  const { nodes, height } = buildWorkflowGraph(events, 'running')
  assert.equal(nodes.find(({ id }) => id === 'exercise_sql').state, 'done')
  assert.equal(nodes.find(({ id }) => id === 'exercise_sql').parent, 'exercise_catalog')
  assert.equal(nodes.find(({ id }) => id === 'database').source, 'SQLite / gym_app.db')
  assert.equal(nodes.find(({ id }) => id === 'database').state, 'active')
  assert.equal(nodes.filter(({ kind }) => kind === 'source').length, 1)
  const connections = buildWorkflowGraph(events, 'running').edges.filter(({ to }) => to === 'database')
  assert.deepEqual(connections.map(({ from, state }) => ({ from, state })), [
    { from: 'routine_sql', state: 'idle' },
    { from: 'exercise_sql', state: 'active' },
    { from: 'history_sql', state: 'idle' },
  ])
  assert.equal(buildWorkflowGraph(events.slice(0, -1), 'running').edges.find(
    ({ id }) => id === 'exercise_sql-database',
  ).state, 'idle')
  assert.equal(nodes.find(({ id }) => id === 'exercise_sql').x, 355)
  assert.ok(branches.filter(({ id }) => id !== 'exercise_explainer').every(
    (branch) => nodes.find(({ id }) => id === branch.id).state === 'idle',
  ))
  assert.ok(height > 560)
  const failed = buildWorkflowGraph(events, 'failed').nodes
  assert.equal(failed.find(({ id }) => id === 'database').state, 'failed')
  assert.equal(buildWorkflowGraph(events, 'failed').edges.find(
    ({ id }) => id === 'exercise_sql-database',
  ).state, 'failed')
  assert.ok(buildWorkflowGraph(events, 'complete').nodes.every(({ state }) => state !== 'active'))
  assert.ok(buildWorkflowGraph([], 'idle').nodes.every(({ state }) => state === 'idle'))
})

test('all SQL branches share one database while keeping independent connection history', () => {
  const queries = ['routine_context', 'exercise_catalog', 'history_search'].map((parent, index) => ({
    ...steps.at(-1), id: `sql_${index}`, parent,
  }))
  const events = playbackEvents(queries, 'running')
  const running = buildWorkflowGraph(events, 'running')
  assert.equal(running.nodes.filter(({ kind }) => kind === 'source').length, 1)
  assert.deepEqual(running.edges.filter(({ to }) => to === 'database').map(({ from, state }) => ({ from, state })), [
    { from: 'routine_sql', state: 'done' },
    { from: 'exercise_sql', state: 'done' },
    { from: 'history_sql', state: 'active' },
  ])
  assert.ok(buildWorkflowGraph(events, 'complete').edges.filter(({ to }) => to === 'database')
    .every(({ state }) => state === 'done'))
  assert.ok(buildWorkflowGraph([], 'idle').edges.every(({ state }) => state === 'idle'))
})

test('entire tree has stable positions before, during, and after execution and fits the available space', () => {
  const idle = buildWorkflowGraph([], 'idle')
  const completed = buildWorkflowGraph(playbackEvents([
    ...steps,
    ...Array.from({ length: 200 }, (_, index) => ({ ...steps.at(-1), id: `sql_${index}` })),
    { id: 'response', label: 'Your response is ready' },
  ], 'complete'), 'complete')
  assert.deepEqual(completed.nodes.map(({ id, x, y }) => ({ id, x, y })),
    idle.nodes.map(({ id, x, y }) => ({ id, x, y })))
  assert.equal(idle.nodes.length, 23)
  assert.equal(idle.edges.length, 24)
  const database = idle.nodes.find(({ id }) => id === 'database')
  assert.equal(database.x, 25)
  assert.equal(database.y, 20)
  assert.ok(idle.nodes.every(({ x, y }) => x >= database.x && y >= database.y))
  for (const id of ['routine_updater', 'routine_build', 'routine_save', 'weekly_performance', 'past_day_exercise', 'compare_last_two_workouts', 'response']) {
    assert.ok(idle.nodes.some((node) => node.id === id))
  }
  for (const size of [{ width: 1000, height: 700 }, { width: 400, height: 250 }, { width: 0, height: 0 }]) {
    const scale = fitWorkflowGraph(size, idle)
    assert.ok(idle.width * scale <= size.width + 0.001)
    assert.ok(idle.height * scale <= size.height + 0.001)
    assert.ok(idle.nodes.every(({ x, y }) => x >= 0 && y >= 0 &&
      (x + 280) * scale <= size.width + 0.001 && (y + 76) * scale <= size.height + 0.001))
  }
})

test('NDJSON keeps SQL metadata across fragmented chunks and rejects invalid metadata', async () => {
  const text = steps.map((step) => JSON.stringify({ type: 'progress', ...step })).join('\n') +
    '\n' + JSON.stringify({ type: 'result', data: { subsystem: 'exercise_explainer', response: 'Ready' } })
  const encoder = new TextEncoder()
  const response = new Response(new ReadableStream({
    /**
     * Splits events across arbitrary chunk boundaries to exercise the line buffer.
     * @param {ReadableStreamDefaultController<Uint8Array>} controller - Test byte stream.
     * @returns {void}
     */
    start(controller) {
      for (let i = 0; i < text.length; i += 13) controller.enqueue(encoder.encode(text.slice(i, i + 13)))
      controller.close()
    },
  }))
  const received = []
  const result = await readChatStream(response, (step) => received.push(step), (key) => key)
  assert.deepEqual(received, steps)
  assert.equal(result.response, 'Ready')
  await assert.rejects(readChatStream(new Response(JSON.stringify({
    type: 'progress', id: 'sql_bad', label: 'SQL', kind: 'sql', sql: 42,
  }) + '\n'), () => {}, (key) => key), /invalid response/)
})

let server
let Monitor
let translations
let chat
const initialGlobals = new Map()
let initialWindow
before(async () => {
  initialWindow = new Window()
  for (const [key, value] of Object.entries({ document: initialWindow.document, localStorage: initialWindow.localStorage })) {
    initialGlobals.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  }
  server = await createServer({ server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom' })
  Monitor = (await server.ssrLoadModule('/src/components/WorkflowMonitor/WorkflowMonitor.jsx')).default
  translations = await server.ssrLoadModule('/src/i18n/index.jsx')
  chat = await server.ssrLoadModule('/src/features/ai-chat/api/chat.jsx')
})
after(async () => {
  await server?.close()
  initialWindow.close()
  for (const [key, descriptor] of initialGlobals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
  }
})

test('chat delivers the unchanged API envelope to the monitor without delaying its result', async () => {
  const response = { subsystem: 'no_system', response: 'API response text' }
  const fetch = mock.method(globalThis, 'fetch', async () => Response.json(response))
  const received = []
  try {
    const result = await chat.requestChat('Hello', 'session', new AbortController().signal, 'EN', undefined, undefined,
      (data) => received.push(data))
    assert.equal(result.content, response.response)
    assert.deepEqual(received, [response])
  } finally {
    fetch.mock.restore()
  }
})

test('automatic routine saves publish both actual API responses with their endpoints', async () => {
  const routine = {
    name: 'Plan', summary: 'Train', recovery: 'Rest',
    days: [{ day: 1, day_type: 'Push', info: 'Warm up', duration_minutes: 30,
      exercises: [{ exercise_id: 1, name: 'Bench press', sets: 3, reps: '8', rest_seconds: 90, notes: '' }] }],
  }
  const envelope = { subsystem: 'routine_maker', response: {
    status: 'save_requested', message: 'Save this plan', routine, draft_id: 'draft-1',
  } }
  const fetch = mock.method(globalThis, 'fetch', async (_url, options) =>
    Response.json(options.method === 'POST' ? envelope : routine))
  const received = []
  try {
    const result = await chat.requestChat('Save it', 'session', new AbortController().signal, 'EN', 1, undefined,
      (data, endpoint) => received.push({ data, endpoint }))
    assert.deepEqual(received, [
      { data: envelope, endpoint: 'POST /{id}/chat' },
      { data: routine, endpoint: 'PUT /users/{user_id}/routine' },
    ])
    assert.equal(result.savedRoutine.name, 'Plan')
  } finally {
    fetch.mock.restore()
  }
})

test('pop-out reports blocking, updates live, follows theme/language, reopens and cleans up', async () => {
  const window = new Window({ url: 'http://localhost' })
  const descriptors = new Map()
  for (const [key, value] of Object.entries({
    window, document: window.document, navigator: window.navigator, localStorage: window.localStorage,
    MutationObserver: window.MutationObserver, IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    descriptors.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  }
  const { createRoot } = await import('react-dom/client')
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  const child = new Window()
  let closed = false
  child.close = () => { closed = true }
  /**
   * Publishes a new request snapshot to the mounted popup launcher.
   * @param {object} trace - Test execution state, including partial idle fixtures.
   * @returns {void}
   */
  const render = (trace) => root.render(createElement(Monitor, { trace }))
  try {
    await act(async () => { await translations.setLanguage('en'); render({ steps: [], status: 'idle', query: '' }) })
    window.open = () => null
    await act(async () => container.querySelector('button').click())
    assert.match(container.querySelector('[role="alert"]').textContent, /blocked/)
    window.open = () => child
    await act(async () => container.querySelector('button').click())
    assert.ok(child.document.querySelector('.workflow-monitor'))
    assert.equal(child.document.querySelectorAll('.workflow-node').length, 23)
    assert.equal(container.querySelector('[role="alert"]'), null)
    mock.timers.enable({ apis: ['setTimeout'] })
    const trace = { id: 'request-1', steps, status: 'complete', query: 'Explain a squat', response: { subsystem: 'exercise_explainer', response: 'Already available' } }
    await act(async () => render(trace))
    assert.match(child.document.body.textContent, /Explain a squat/)
    assert.ok(child.document.querySelector('.workflow-node.active'))
    assert.match(child.document.querySelector('.workflow-api-response').textContent, /Already available/)
    assert.match(child.document.querySelector('[role="status"]').textContent, /Playing execution/)
    assert.equal(child.document.querySelectorAll('.workflow-node').length, 23)
    assert.equal(child.document.querySelectorAll('.workflow-event-log details').length, 1)
    await act(async () => mock.timers.tick(999))
    assert.equal(child.document.querySelector('[data-node-id="orchestrator"]').classList.contains('idle'), true)
    await act(async () => mock.timers.tick(1))
    assert.equal(child.document.querySelector('[data-node-id="orchestrator"]').classList.contains('active'), true)
    for (let index = 0; index < 3; index++) await act(async () => mock.timers.tick(1000))
    assert.equal(child.document.querySelector('[data-node-id="exercise_sql"]').classList.contains('active'), true)
    await act(async () => child.document.querySelector('[data-node-id="exercise_sql"]').click())
    assert.match(child.document.querySelector('.workflow-inspector pre').textContent, /WHERE id = \?/)
    await act(async () => {
      document.documentElement.className = 'dark'
      await translations.setLanguage('es')
    })
    assert.equal(closed, false)
    assert.equal(child.document.documentElement.className, 'dark')
    assert.equal(child.document.documentElement.lang, 'es')
    assert.match(child.document.body.textContent, /Consulta SQL/)
    await act(async () => render({ ...trace, status: 'failed', error: 'Connection lost' }))
    assert.match(child.document.querySelector('[role="alert"]').textContent, /Connection lost/)
    await act(async () => mock.timers.tick(1000))
    assert.equal(child.document.querySelector('[data-node-id="database"]').classList.contains('active'), true)
    await act(async () => mock.timers.tick(1000))
    assert.equal(child.document.querySelector('[data-node-id="database"]').classList.contains('failed'), true)
    await act(async () => render({ id: 'request-2', steps: [], status: 'running', query: 'Next request' }))
    assert.equal(child.document.querySelectorAll('.workflow-event-log details').length, 1)
    assert.equal(child.document.querySelectorAll('.workflow-node.done').length, 0)
    await act(async () => render({ id: 'request-2', steps: steps.slice(0, 1), status: 'running', query: 'Next request' }))
    await act(async () => mock.timers.tick(500))
    await act(async () => render({ id: 'request-2', steps, status: 'running', query: 'Next request' }))
    await act(async () => mock.timers.tick(499))
    assert.equal(child.document.querySelector('[data-node-id="orchestrator"]').classList.contains('idle'), true)
    await act(async () => mock.timers.tick(1))
    assert.equal(child.document.querySelector('[data-node-id="orchestrator"]').classList.contains('active'), true)
    await act(async () => child.dispatchEvent(new child.Event('beforeunload')))
    assert.equal(child.document.querySelector('.workflow-monitor'), null)
    closed = false
    await act(async () => container.querySelector('button').click())
    assert.ok(child.document.querySelector('.workflow-monitor'))
    await act(async () => root.unmount())
    assert.equal(closed, true)
  } finally {
    mock.timers.reset()
    window.close()
    for (const [key, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
})
