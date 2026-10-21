/**
 * @file Regression tests for saved-plan summaries and seven-day workout activity.
 * Vite-loaded production modules run in happy-dom against independently mocked
 * routine/history endpoints, covering timing estimates, calendar validation,
 * localization, cancellation, retries, and profile isolation.
 */
import assert from 'node:assert/strict'
import { after, afterEach, before, beforeEach, test, mock } from 'node:test'
import { act, createElement } from 'react'
import { Window } from 'happy-dom'
import { createServer } from 'vite'

let server
let window
let root
let createRoot
let TrainingPanel
let translations
let getWeeklyProgress
let getUserDays
let getPlannedSessionMinutes
const originals = new Map()
const plan = {
  name: 'Weekly plan', recovery: 'Rest between sessions.',
  days: [35, 65, 45].map((duration_minutes, index) => ({
    day: index + 1, day_type: `Day ${index + 1}`, info: 'Warm up.',
    duration_minutes,
    exercises: [{ exercise_id: 1, name: 'Squat', sets: 3, reps: '8', rest_seconds: 60, notes: '' }],
  })),
}
const days = [
  ['2026-10-11', 'Sunday', false],
  ['2026-10-12', 'Monday', true],
  ['2026-10-13', 'Tuesday', false],
  ['2026-10-14', 'Wednesday', true],
  ['2026-10-15', 'Thursday', false],
  ['2026-10-16', 'Friday', false],
  ['2026-10-17', 'Saturday', true],
].map(([date, day_of_week, has_routine]) => ({ date, day_of_week, has_routine }))

before(async () => {
  window = new Window({ url: 'http://localhost' })
  for (const [key, value] of Object.entries({
    window, document: window.document, navigator: window.navigator,
    localStorage: window.localStorage, IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  }
  createRoot = (await import('react-dom/client')).createRoot
  server = await createServer({ server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom' })
  translations = await server.ssrLoadModule('/src/i18n/index.jsx')
  TrainingPanel = (await server.ssrLoadModule('/src/components/TrainingPanel/TrainingPanel.jsx')).default
  ;({ getWeeklyProgress } = await server.ssrLoadModule('/src/features/TrainingPanel/weekly-progress/getWeeklyProgress.jsx'))
  ;({ getUserDays } = await server.ssrLoadModule('/src/hooks/session/users.js'))
  ;({ getPlannedSessionMinutes } = await server.ssrLoadModule('/src/features/RoutineMaker/routine-data/routineData.js'))
})

beforeEach(async () => {
  await translations.setLanguage('en')
  const container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  mockDays(async () => Response.json(days))
})

afterEach(async () => {
  await act(async () => root.unmount())
  document.body.replaceChildren()
  mock.restoreAll()
})

after(async () => {
  await server?.close()
  window?.close()
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
  }
})

/**
 * Stubs history requests while preserving the standard saved-plan fixture.
 * @param {(url: string, options: RequestInit) => Promise<Response>} handler - History responder.
 * @returns {Function} Node test mock for fetch.
 */
function mockDays(handler) {
  return mock.method(globalThis, 'fetch', (url, options) =>
    url.endsWith('/routine') ? Response.json(plan) : handler(url, options))
}

/**
 * Stubs routine requests while preserving the standard seven-day history fixture.
 * @param {(url: string, options: RequestInit) => Promise<Response>} handler - Routine responder.
 * @returns {Function} Node test mock for fetch.
 */
function mockRoutine(handler) {
  return mock.method(globalThis, 'fetch', (url, options) =>
    url.endsWith('/routine') ? handler(url, options) : Response.json(days))
}

/**
 * Mounts/updates the sidebar with profile-keyed state and an optional refresh token.
 * @param {number} [userId=7] - Selected test profile.
 * @param {unknown} [routineRevision] - Dependency token used to trigger routine reads.
 * @returns {Promise<void>} Resolves after React effects settle.
 */
async function render(userId = 7, routineRevision) {
  await act(async () => root.render(createElement(TrainingPanel, {
    key: userId, userId, routineRevision, onOpen: () => {}, onPrompt: () => {},
  })))
}

test('routine card loads the selected user’s plan and displays its day count and maximum duration', async () => {
  mockRoutine(async (url, options) => {
    assert.equal(url, '/api/users/7/routine')
    assert.ok(options.signal instanceof AbortSignal)
    return Response.json(plan)
  })
  await render()
  assert.deepEqual(
    [...document.querySelectorAll('.training-stats strong')].map((element) => element.textContent),
    ['3 days', '65 min'],
  )
  assert.match(document.querySelector('.training-card').textContent, /Max session duration/)
  assert.doesNotMatch(document.querySelector('.training-card').textContent, /Estimated/)
  await act(async () => translations.setLanguage('es'))
  assert.match(document.querySelector('.training-card').textContent, /3 días/)
  assert.match(document.querySelector('.training-card').textContent, /Duración máxima por sesión/)
})

test('routine card refreshes its count and maximum when the saved plan changes', async () => {
  await render(7, 1)
  mockRoutine(async () => Response.json({ ...plan, days: plan.days.slice(0, 1) }))
  await render(7, 2)
  assert.deepEqual(
    [...document.querySelectorAll('.training-stats strong')].map((element) => element.textContent),
    ['1 days', '35 min'],
  )
})

test('routine loading and missing plans do not display fabricated stats', async () => {
  let resolve
  mockRoutine(() => new Promise((done) => { resolve = done }))
  await render()
  const card = document.querySelector('.training-card')
  assert.match(card.querySelector('[role="status"]').textContent, /Loading your routine/)
  assert.equal(card.querySelector('.training-stats'), null)
  await act(async () => resolve(Response.json(null)))
  assert.match(card.textContent, /No saved routine yet/)
  assert.equal(card.querySelector('.training-stats'), null)
})

test('routine failures and malformed plans are visible and retryable', async () => {
  for (const response of [
    () => Response.json({ detail: 'Unavailable' }, { status: 503 }),
    () => Response.json({ ...plan, days: [] }),
  ]) {
    mockRoutine(async () => response())
    await render(7, response)
    const card = document.querySelector('.training-card')
    assert.match(card.querySelector('[role="alert"]').textContent, /Could not load routine/)
    assert.equal(card.querySelector('.training-stats'), null)
    mockRoutine(async () => Response.json(plan))
    await act(async () => card.querySelector('.retry-button').click())
    assert.equal(card.querySelector('[role="alert"]'), null)
    assert.match(card.querySelector('.training-stats').textContent, /65 min/)
  }
})

test('legacy routines estimate the longest planned session and clearly label the estimate', async () => {
  const legacy = {
    ...plan, storage_format: 'legacy',
    days: plan.days.map((day) => ({
      ...day, routine_id: day.day, duration_minutes: null,
      exercises: day.exercises.map((exercise) => ({
        ...exercise, sets: day.day === 2 ? 6 : 3, rest_seconds: null,
      })),
    })),
  }
  mockRoutine(async () => Response.json(legacy))
  await render()
  assert.deepEqual(
    [...document.querySelectorAll('.training-stats strong')].map((element) => element.textContent),
    ['3 days', '17 min'],
  )
  assert.match(document.querySelector('.training-card').textContent, /Estimated max session/)
  assert.match(document.querySelector('.training-stats [title]').title, /Recorded workouts are not used/)
  mock.method(globalThis, 'fetch', async (url) => Response.json(
    url.endsWith('/routine') ? legacy : days.map((day) => ({ ...day, has_routine: true }))))
  await act(async () => root.render(null))
  await render()
  assert.match(document.querySelector('.training-stats').textContent, /17 min/)
  await act(async () => translations.setLanguage('es'))
  assert.match(document.querySelector('.training-card').textContent, /Sesión máxima estimada/)
})

test('planned duration estimates include warm-up, sets, rests, transitions and round up', () => {
  const day = {
    duration_minutes: null,
    exercises: [{ sets: 3, rest_seconds: null }],
  }
  const before = structuredClone(day)
  assert.equal(getPlannedSessionMinutes(day), 11)
  assert.deepEqual(day, before)
  assert.equal(getPlannedSessionMinutes({ ...day, exercises: [{ sets: 1, rest_seconds: null }] }), 6)
  assert.equal(getPlannedSessionMinutes({ ...day, exercises: [day.exercises[0], day.exercises[0]] }), 17)
  assert.equal(getPlannedSessionMinutes({ ...day, duration_minutes: 42.5 }), 42.5)
})

test('switching users ignores a stale routine response', async () => {
  let resolveFirst
  let firstSignal
  mockRoutine(async (url, options) => {
    if (url === '/api/users/7/routine') {
      firstSignal = options.signal
      return new Promise((resolve) => { resolveFirst = resolve })
    }
    assert.equal(url, '/api/users/8/routine')
    return Response.json({ ...plan, days: plan.days.slice(0, 1) })
  })
  await render(7)
  await render(8)
  assert.equal(firstSignal.aborted, true)
  await act(async () => resolveFirst(Response.json(plan)))
  assert.deepEqual(
    [...document.querySelectorAll('.training-stats strong')].map((element) => element.textContent),
    ['1 days', '35 min'],
  )
})

test('Saturday ends a seven-day Sunday–Saturday history with real workout markers', async () => {
  mockDays(async (url, options) => {
    assert.equal(url, '/api/users/7/days')
    assert.ok(options.signal instanceof AbortSignal)
    return Response.json([...days].reverse())
  })
  await render()
  const cells = [...document.querySelectorAll('.week-days > div')]
  assert.equal(cells.length, 7)
  assert.deepEqual(cells.map((cell) => cell.dataset.date), days.map((day) => day.date))
  assert.deepEqual(cells.map((cell) => cell.firstElementChild.textContent), ['S', 'M', 'T', 'W', 'T', 'F', 'S'])
  assert.deepEqual(cells.map((cell) => Boolean(cell.querySelector('.training-day'))), days.map((day) => day.has_routine))
  assert.equal(cells.at(-1).getAttribute('aria-current'), 'date')
  assert.match(document.querySelector('.week-card').textContent, /3 training days logged/)
  assert.ok(document.querySelector('[aria-label="Workout logged on 2026-10-17"]'))
})

test('Spanish weekdays use the date rather than a Monday-first fixed position', async () => {
  await translations.setLanguage('es')
  await render()
  assert.deepEqual(
    [...document.querySelectorAll('.week-days > div > span:first-child')].map((cell) => cell.textContent),
    ['D', 'L', 'M', 'X', 'J', 'V', 'S'],
  )
  assert.match(document.querySelector('.week-card').textContent, /3 días de entrenamiento registrados/)
})

test('loading does not present fabricated no-workout days', async () => {
  let resolve
  mockDays(() => new Promise((done) => { resolve = done }))
  await render()
  assert.match(document.querySelector('[role="status"]').textContent, /Loading weekly rhythm/)
  assert.equal(document.querySelector('.week-days'), null)
  await act(async () => resolve(Response.json(days)))
  assert.equal(document.querySelector('[role="status"]'), null)
  assert.equal(document.querySelectorAll('.week-days > div').length, 7)
})

test('API errors are visible and retry reloads the actual history', async () => {
  mockDays(async () => Response.json({ detail: 'Unavailable' }, { status: 503 }))
  await render()
  assert.match(document.querySelector('[role="alert"]').textContent, /HTTP 503/)
  assert.equal(document.querySelector('.week-days'), null)
  mockDays(async () => Response.json(days.map((day) => ({ ...day, has_routine: false }))))
  await act(async () => document.querySelector('.week-card button').click())
  assert.equal(document.querySelector('[role="alert"]'), null)
  assert.equal(document.querySelectorAll('.training-day').length, 0)
  assert.match(document.querySelector('.week-card').textContent, /0 training days logged/)
})

test('switching users aborts stale requests and does not reuse another user’s days', async () => {
  let resolveFirst
  let firstSignal
  mockDays(async (url, options) => {
    if (url === '/api/users/7/days') {
      firstSignal = options.signal
      return new Promise((resolve) => { resolveFirst = resolve })
    }
    assert.equal(url, '/api/users/8/days')
    return Response.json(days.map((day) => ({ ...day, has_routine: false })))
  })
  await render(7)
  await render(8)
  assert.equal(firstSignal.aborted, true)
  await act(async () => resolveFirst(Response.json(days)))
  assert.equal(document.querySelectorAll('.training-day').length, 0)
  assert.match(document.querySelector('.week-card').textContent, /0 training days logged/)
})

test('remounting after a workout reloads history', async () => {
  await render()
  await act(async () => root.render(null))
  mockDays(async () => Response.json(days.map((day) => ({ ...day, has_routine: true }))))
  await render()
  assert.equal(document.querySelectorAll('.training-day').length, 7)
})

test('malformed activity produces an explicit error instead of false markers', async () => {
  mockDays(async () => Response.json({ days }))
  await render()
  assert.match(document.querySelector('[role="alert"]').textContent, /invalid days/)
  assert.equal(document.querySelector('.week-days'), null)
})

test('progress validates exactly seven consecutive calendar dates without changing input', () => {
  const before = structuredClone(days)
  assert.equal(getWeeklyProgress(days).completed, 3)
  assert.deepEqual(days, before)
  for (const invalid of [
    null, [], days.slice(1), [...days, days[0]],
    days.map((day) => ({ ...day, has_routine: 'false' })),
    days.map((day) => ({ ...day, date: '2026-02-30' })),
    [days[0], days[0], ...days.slice(2)],
    [...days.slice(0, 6), { ...days[6], date: '2026-10-18' }],
  ]) assert.throws(() => getWeeklyProgress(invalid), /invalid days/)
  const dates = ['2028-02-25', '2028-02-26', '2028-02-27', '2028-02-28', '2028-02-29', '2028-03-01', '2028-03-02']
  assert.equal(getWeeklyProgress(dates.map((date) => ({ date, has_routine: false }))).weekDays.length, 7)
})

test('invalid user IDs fail before making a request', async () => {
  const fetch = mock.method(globalThis, 'fetch', async () => Response.json(days))
  for (const id of [0, -1, '7', undefined]) {
    await assert.rejects(getUserDays(id), /positive integer/)
  }
  assert.equal(fetch.mock.callCount(), 0)
})
