/**
 * @file Regression tests for structured browser logging and error recovery.
 * Captures console records to verify severity, timing, metadata allowlisting, and
 * private-data exclusion while mocked HTTP/stream failures preserve caller behavior.
 * Browser listeners and React boundaries are exercised in an isolated DOM.
 */
import assert from 'node:assert/strict'
import { after, afterEach, before, beforeEach, mock, test } from 'node:test'
import { act, createElement } from 'react'
import { Window } from 'happy-dom'
import { createServer } from 'vite'

let server
let window
let logging
let http
let browser
let ErrorBoundary
let translations
let chat
let records
const originals = new Map()

before(async () => {
  window = new Window({ url: 'http://localhost' })
  for (const [key, value] of Object.entries({
    window, document: window.document, localStorage: window.localStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  }
  server = await createServer({ server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom' })
  logging = await server.ssrLoadModule('/src/lib/observability/logger.js')
  http = await server.ssrLoadModule('/src/lib/observability/http.js')
  browser = await server.ssrLoadModule('/src/lib/observability/browser.js')
  translations = await server.ssrLoadModule('/src/i18n/index.jsx')
  ErrorBoundary = (await server.ssrLoadModule('/src/components/ErrorBoundary/ErrorBoundary.jsx')).default
  chat = await server.ssrLoadModule('/src/features/ai-chat/api/chat.jsx')
})

beforeEach(() => {
  records = []
  logging.configureLogging('debug')
  for (const level of ['debug', 'info', 'warn', 'error']) {
    mock.method(console, level, (record) => records.push(record))
  }
})

afterEach(() => mock.restoreAll())

after(async () => {
  await server?.close()
  window?.close()
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
  }
})

test('logger filters levels and metadata and emits a stable structured record', () => {
  const logger = logging.createLogger('test')
  logging.configureLogging('warn')
  logger.info('ignored')
  logger.warn('operation.failed', {
    status: 422, duration_ms: 42, outcome: 'failed',
    error: new Error('private'), body: 'private', user_id: 123, url: '/private?secret=1',
  })
  assert.equal(records.length, 1)
  assert.deepEqual(Object.keys(records[0]).sort(), [
    'timestamp', 'level', 'scope', 'event', 'status', 'duration_ms', 'outcome',
  ].sort())
  assert.equal(records[0].level, 'warn')
  assert.equal(records[0].scope, 'test')
  assert.equal(records[0].event, 'operation.failed')
  assert.equal(records[0].duration_ms, 42)
  assert.ok(Number.isFinite(Date.parse(records[0].timestamp)))
  assert.ok(!JSON.stringify(records).includes('private'))
  logging.configureLogging('off')
  logger.error('ignored')
  assert.equal(records.length, 1)
  assert.throws(() => logging.configureLogging('invalid'), RangeError)
  logging.configureLogging('debug')
  logger.debug('visible')
  assert.equal(records[1].level, 'debug')
  assert.equal(logging.errorType(new TypeError('private')), 'TypeError')
  assert.equal(logging.errorType({ name: 'private' }), 'UnknownError')
  assert.equal(logging.errorType('private'), 'UnknownError')
})

test('HTTP records exact header latency and severity without consuming or changing responses', async () => {
  let clock = 0
  mock.method(performance, 'now', () => { clock += 42; return clock })
  for (const [status, level] of [[200, 'info'], [404, 'warn'], [503, 'error']]) {
    const response = new Response('private response', { status })
    const options = { method: 'POST', body: 'private body', headers: { Authorization: 'private token' } }
    const fetch = mock.method(globalThis, 'fetch', async (input, init) => {
      assert.equal(input, '/api/users/123?secret=private')
      assert.equal(init, options)
      return response
    })
    assert.equal(await http.observedFetch('/users/{user_id}', '/api/users/123?secret=private', options), response)
    assert.equal(response.bodyUsed, false)
    assert.deepEqual(records.at(-1), {
      timestamp: records.at(-1).timestamp, scope: 'http', level, event: 'http.response',
      route: '/users/{user_id}', method: 'POST', status, duration_ms: 42,
      outcome: status === 200 ? 'success' : 'failed',
    })
    fetch.mock.restore()
  }
  assert.ok(!JSON.stringify(records).includes('private'))
})

test('HTTP preserves failures and distinguishes network, timeout, and cancellation', async () => {
  for (const [error, level, outcome] of [
    [new TypeError('private host'), 'error', 'failed'],
    [new DOMException('private', 'TimeoutError'), 'warn', 'timeout'],
    [new DOMException('private', 'AbortError'), 'debug', 'cancelled'],
  ]) {
    const fetch = mock.method(globalThis, 'fetch', async () => { throw error })
    await assert.rejects(http.observedFetch('/health', '/api/health'), (received) => received === error)
    assert.equal(records.at(-1).level, level)
    assert.equal(records.at(-1).outcome, outcome)
    assert.equal(records.at(-1).error_type, error.name)
    assert.equal(records.at(-1).method, 'GET')
    fetch.mock.restore()
  }
  const controller = new AbortController()
  controller.abort(new Error('private cancellation reason'))
  mock.method(globalThis, 'fetch', async () => { throw controller.signal.reason })
  await assert.rejects(http.observedFetch('/health', '/api/health', { signal: controller.signal }))
  assert.equal(records.at(-1).outcome, 'cancelled')
  assert.ok(!JSON.stringify(records).includes('private'))
})

test('operations measure completion and preserve results, stream failures, and timeout reasons', async () => {
  let clock = 0
  mock.method(performance, 'now', () => clock)
  const result = { response: 'private' }
  assert.equal(await http.observeOperation('chat.read_response', async () => {
    clock = 1250
    return result
  }), result)
  assert.equal(records.at(-1).duration_ms, 1250)
  assert.equal(records.at(-1).outcome, 'success')
  const error = new SyntaxError('private response')
  await assert.rejects(http.observeOperation('chat.read_response', async () => { throw error }), (received) => received === error)
  assert.equal(records.at(-1).level, 'error')
  const controller = new AbortController()
  controller.abort(new DOMException('private', 'TimeoutError'))
  await assert.rejects(http.observeOperation('chat.read_response', async () => { throw error }, controller.signal))
  assert.equal(records.at(-1).outcome, 'timeout')
  assert.ok(!JSON.stringify(records).includes('private'))
})

test('chat logs header and streamed-response latency separately without logging private content', async () => {
  let clock = 0
  mock.method(performance, 'now', () => clock)
  const encoder = new TextEncoder()
  mock.method(globalThis, 'fetch', async () => {
    clock = 15
    return new Response(new ReadableStream({
      /**
       * Supplies private fixture events to verify stream timing without payload logging.
       * @param {ReadableStreamDefaultController<Uint8Array>} controller - Test byte stream.
       * @returns {void}
       */
      start(controller) {
        controller.enqueue(encoder.encode([
          JSON.stringify({ type: 'progress', id: 'private-step', label: 'private progress' }),
          JSON.stringify({ type: 'result', data: { subsystem: 'no_system', response: 'private answer' } }),
          '',
        ].join('\n')))
        controller.close()
      },
    }), { headers: { 'Content-Type': 'application/x-ndjson' } })
  })
  const result = await chat.requestChat('private prompt', 'private-session', new AbortController().signal, 'EN', 123,
    () => { clock = 1215 })
  assert.equal(result.content, 'private answer')
  assert.equal(result.steps[0].label, 'private progress')
  assert.equal(records.length, 2)
  assert.equal(records[0].event, 'http.response')
  assert.equal(records[0].route, '/{id}/chat')
  assert.equal(records[0].duration_ms, 15)
  assert.equal(records[1].event, 'chat.read_response')
  assert.equal(records[1].duration_ms, 1200)
  assert.equal(records[1].outcome, 'success')
  assert.ok(!JSON.stringify(records).includes('private'))
})

test('chat stream errors are logged even when the HTTP status is successful', async () => {
  mock.method(globalThis, 'fetch', async () => new Response(
    `${JSON.stringify({ type: 'error', status: 500, message: 'private backend detail' })}\n`,
    { headers: { 'Content-Type': 'application/x-ndjson' } },
  ))
  await assert.rejects(chat.requestChat('private', 'private-session', new AbortController().signal, 'EN', 123))
  assert.equal(records[0].status, 200)
  assert.equal(records[1].event, 'chat.read_response')
  assert.equal(records[1].level, 'error')
  assert.equal(records[1].outcome, 'failed')
  assert.ok(!JSON.stringify(records).includes('private'))
})

test('browser listeners initialize once, do not suppress errors, and clean up for reinitialization', () => {
  const dispose = browser.initializeObservability(window)
  assert.equal(browser.initializeObservability(window), dispose)
  const error = new window.ErrorEvent('error', { error: new Error('private'), message: 'private', cancelable: true })
  window.dispatchEvent(error)
  const rejection = new window.Event('unhandledrejection', { cancelable: true })
  Object.defineProperty(rejection, 'reason', { value: 'private rejection' })
  window.dispatchEvent(rejection)
  assert.deepEqual(records.map(({ event }) => event), ['browser.uncaught_error', 'browser.unhandled_rejection'])
  assert.equal(error.defaultPrevented, false)
  assert.equal(rejection.defaultPrevented, false)
  assert.ok(!JSON.stringify(records).includes('private'))
  dispose()
  window.dispatchEvent(error)
  assert.equal(records.length, 2)
  const nextDispose = browser.initializeObservability(window)
  window.dispatchEvent(error)
  assert.equal(records.length, 3)
  nextDispose()
})

test('browser rejection capture records safe error types and cancellation severity', () => {
  const dispose = browser.initializeObservability(window)
  try {
    for (const reason of [new TypeError('private'), new DOMException('private', 'AbortError')]) {
      const event = new window.Event('unhandledrejection')
      Object.defineProperty(event, 'reason', { value: reason })
      window.dispatchEvent(event)
    }
    assert.deepEqual(records.map(({ level, error_type }) => ({ level, error_type })), [
      { level: 'error', error_type: 'TypeError' },
      { level: 'debug', error_type: 'AbortError' },
    ])
    assert.ok(!JSON.stringify(records).includes('private'))
  } finally {
    dispose()
  }
})

test('React boundary preserves healthy content and shows a localized reload fallback on crashes', async () => {
  const { createRoot } = await import('react-dom/client')
  const reload = mock.method(window.location, 'reload', () => {})
  /**
   * Intentionally crashes descendant rendering to test the boundary's safe fallback.
   * Accepts no props and reads no state.
   * @returns {never}
   * @throws {TypeError} Always throws private fixture text that must not be logged.
   */
  function Broken() { throw new TypeError('private render data') }
  for (const [language, title, button] of [
    ['en', 'Something went wrong', 'Reload app'],
    ['es', 'Algo sali\u00f3 mal', 'Recargar aplicaci\u00f3n'],
  ]) {
    await translations.setLanguage(language)
    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container, { onCaughtError: () => {} })
    try {
      await act(async () => root.render(createElement(ErrorBoundary, null, createElement('p', null, 'Healthy'))))
      assert.equal(container.textContent, 'Healthy')
      await act(async () => root.render(createElement(ErrorBoundary, null, createElement(Broken))))
      assert.equal(container.querySelector('[role="alert"] h1').textContent, title)
      assert.equal(container.querySelector('button').textContent, button)
      assert.equal(records.at(-1).event, 'react.render_failed')
      assert.equal(records.at(-1).error_type, 'TypeError')
      assert.ok(!container.textContent.includes('private'))
      await act(async () => container.querySelector('button').click())
    } finally {
      await act(async () => root.unmount())
      container.remove()
    }
  }
  assert.equal(reload.mock.callCount(), 2)
  assert.ok(!JSON.stringify(records).includes('private'))
})
