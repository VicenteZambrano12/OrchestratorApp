import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { act, createElement } from 'react'
import { Window } from 'happy-dom'
import { createServer } from 'vite'
import { buildWorkflowGraph, branches } from './workflowGraph.js'
import { readChatStream } from '../../features/ai-chat/api/readChatStream.js'

const steps = [
  { id: 'orchestrator', label: 'Analyzing your request' },
  { id: 'exercise_explainer', label: 'Identifying the exercises to explain' },
  { id: 'exercise_catalog', label: 'Searching the exercise catalog' },
  { id: 'sql_1', label: 'Executing SQL query', kind: 'sql', parent: 'exercise_catalog', sql: 'SELECT * FROM dim_exercises WHERE id = ?', source: 'SQLite / gym_app.db' },
]

test('graph highlights only the executed branch and attaches SQL and source nodes', () => {
  const { nodes, height } = buildWorkflowGraph(steps, 'running')
  assert.equal(nodes.find(({ id }) => id === 'sql_1').state, 'active')
  assert.equal(nodes.find(({ id }) => id === 'sql_1').parent, 'exercise_catalog')
  assert.equal(nodes.find(({ id }) => id === 'sql_1_source').label, 'SQLite / gym_app.db')
  assert.equal(nodes.find(({ id }) => id === 'sql_1_source').parent, 'sql_1')
  assert.ok(nodes.filter(({ branch }) => branch === 'exercise_explainer').every(({ x }) => x === 355))
  assert.ok(branches.filter(({ id }) => id !== 'exercise_explainer').every(
    (branch) => nodes.find(({ id }) => id === branch.id).state === 'idle',
  ))
  assert.ok(height > 560)
  const failed = buildWorkflowGraph(steps, 'failed').nodes
  assert.equal(failed.find(({ id }) => id === 'sql_1').state, 'failed')
  assert.equal(failed.find(({ id }) => id === 'sql_1_source').state, 'failed')
  assert.ok(buildWorkflowGraph(steps, 'complete').nodes.every(({ state }) => state !== 'active'))
  assert.ok(buildWorkflowGraph([], 'idle').nodes.every(({ state }) => state === 'idle'))
})

test('NDJSON keeps SQL metadata across fragmented chunks and rejects invalid metadata', async () => {
  const text = steps.map((step) => JSON.stringify({ type: 'progress', ...step })).join('\n') +
    '\n' + JSON.stringify({ type: 'result', data: { subsystem: 'exercise_explainer', response: 'Ready' } })
  const encoder = new TextEncoder()
  const response = new Response(new ReadableStream({
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
})
after(async () => {
  await server?.close()
  initialWindow.close()
  for (const [key, descriptor] of initialGlobals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
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
  const render = (trace) => root.render(createElement(Monitor, { trace }))
  try {
    await act(async () => { await translations.setLanguage('en'); render({ steps: [], status: 'idle', query: '' }) })
    window.open = () => null
    await act(async () => container.querySelector('button').click())
    assert.match(container.querySelector('[role="alert"]').textContent, /blocked/)
    window.open = () => child
    await act(async () => container.querySelector('button').click())
    assert.ok(child.document.querySelector('.workflow-monitor'))
    assert.equal(container.querySelector('[role="alert"]'), null)
    await act(async () => render({ steps, status: 'running', query: 'Explain a squat' }))
    assert.match(child.document.body.textContent, /Explain a squat/)
    assert.ok(child.document.querySelector('.workflow-node.active'))
    await act(async () => [...child.document.querySelectorAll('.workflow-node')].find(
      (node) => node.textContent.includes('SQL query'),
    ).click())
    assert.match(child.document.querySelector('pre').textContent, /WHERE id = \?/)
    await act(async () => {
      document.documentElement.className = 'dark'
      await translations.setLanguage('es')
    })
    assert.equal(closed, false)
    assert.equal(child.document.documentElement.className, 'dark')
    assert.equal(child.document.documentElement.lang, 'es')
    assert.match(child.document.body.textContent, /Consulta SQL/)
    await act(async () => render({ steps, status: 'failed', query: 'Explain a squat', error: 'Connection lost' }))
    assert.match(child.document.querySelector('[role="alert"]').textContent, /Connection lost/)
    await act(async () => child.dispatchEvent(new child.Event('beforeunload')))
    assert.equal(child.document.querySelector('.workflow-monitor'), null)
    closed = false
    await act(async () => container.querySelector('button').click())
    assert.ok(child.document.querySelector('.workflow-monitor'))
    await act(async () => root.unmount())
    assert.equal(closed, true)
  } finally {
    window.close()
    for (const [key, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
})
