import assert from 'node:assert/strict'
import { after, afterEach, before, beforeEach, test } from 'node:test'
import { act, createElement } from 'react'
import { Window } from 'happy-dom'
import { createServer } from 'vite'

let server
let window
let root
let createRoot
let MainView
let ThemeContext
let translations
const originals = new Map()
const user = { id: 7, username: 'Test User' }
const plan = {
  name: 'Saved plan', summary: 'Train consistently.', recovery: 'Rest between days.',
  days: [{
    day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
    exercises: [
      { exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' },
      { exercise_id: 2, name: 'Overhead Press', sets: 2, reps: '10', rest_seconds: 60, notes: '' },
    ],
  }],
}

before(async () => {
  window = new Window({ url: 'http://localhost' })
  for (const [key, value] of Object.entries({
    window, document: window.document, navigator: window.navigator,
    localStorage: window.localStorage, FormData: window.FormData,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  }
  createRoot = (await import('react-dom/client')).createRoot
  server = await createServer({ server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom' })
  translations = await server.ssrLoadModule('/src/i18n/index.jsx')
  MainView = (await server.ssrLoadModule('/src/pages/MainView/MainView.jsx')).default
  ThemeContext = (await server.ssrLoadModule('/src/hooks/theme/ThemeContext.jsx')).ThemeContext
})

beforeEach(async () => {
  await translations.setLanguage('en')
  const container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  await act(async () => {
    root.render(createElement(ThemeContext.Provider, {
      value: { theme: 'light', resolvedTheme: 'light', setTheme: () => {} },
    }, createElement(MainView, { user, onSwitchUser: () => {} })))
  })
})

afterEach(async () => {
  await act(async () => root.unmount())
  document.body.replaceChildren()
})

after(async () => {
  await server?.close()
  window?.close()
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
  }
})

function button(text, scope = document) {
  const found = [...scope.querySelectorAll('button')].find((element) => element.textContent.trim() === text)
  assert.ok(found, `Missing button: ${text}`)
  return found
}

async function click(text, scope) {
  await act(async () => button(text, scope).click())
}

function routineResponse(routine, id = 42) {
  return Response.json(routine, { headers: { 'X-Routine-Id': String(id) } })
}

async function changeInput(label, value, scope = document) {
  await act(async () => {
    const input = scope.querySelector(`input[aria-label="${label}"]`)
    assert.ok(input, `Missing input: ${label}`)
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value)
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
}

async function changeSets(value) {
  await act(async () => {
    const input = document.querySelector('input[aria-label="Bench Press sets"]')
    assert.ok(input)
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value)
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
}

test('legacy templates load with unknown timing and log against the selected original routine', async (context) => {
  const legacy = {
    ...structuredClone(plan),
    storage_format: 'legacy',
    days: [9, 11].map((routineId, index) => ({
      ...structuredClone(plan.days[0]),
      day: index + 1, routine_id: routineId, duration_minutes: null,
      day_type: index === 0 ? 'Legacy push' : 'Legacy legs',
      exercises: [{ ...plan.days[0].exercises[0], rest_seconds: null }],
    })),
  }
  const posts = []
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url.endsWith('/routine')) {
      assert.notEqual(options.method, 'PUT')
      return routineResponse(legacy, 11)
    }
    assert.equal(url, '/api/users/7/workouts')
    const payload = JSON.parse(options.body)
    posts.push(payload)
    return Response.json({
      training_id: `legacy-${posts.length}`, user_id: 7, routine_id: payload.routine_id,
      date: '2026-10-15', created_at: '2026-10-15T15:00:00Z', sets_saved: payload.sets.length,
    })
  })
  await click('My Routine')
  assert.equal(document.querySelector('[role="alert"]'), null)
  assert.match(document.querySelector('.routine-badges').textContent, /Unknown/)
  assert.match(document.querySelector('.exercise-name small').textContent, /Unknown/)
  assert.equal(button('Edit workout').disabled, true)
  assert.match(document.querySelector('.routine-view').textContent, /create a new plan to edit/)
  for (const [index, routineId] of [9, 11].entries()) {
    await act(async () => document.querySelectorAll('[role="tab"]')[index].click())
    await click('Start Workout')
    await changeInput('Bench Press set 1 reps', '8')
    await act(async () => document.querySelector('[aria-label="Mark Bench Press complete"]').click())
    assert.equal(document.querySelector('[aria-label="Rest countdown"]'), null)
    assert.equal(document.querySelector('[role="alert"]'), null)
    await click('Finish workout')
    await click('Yes, finish and save', document.querySelector('dialog[open]'))
    assert.equal(posts.at(-1).routine_id, routineId)
  }
})

test('Done editing asks before PUT; cancel preserves edits; confirmation saves exactly once', async (context) => {
  let currentPlan = structuredClone(plan)
  let finishSave
  const puts = []
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/users/7/routine')
    if (options.method !== 'PUT') return routineResponse(currentPlan)
    puts.push(JSON.parse(options.body))
    return new Promise((resolve) => {
      finishSave = () => { currentPlan = puts.at(-1); resolve(routineResponse(currentPlan)) }
    })
  })
  await click('My Routine')
  await changeSets('4')
  await click('Edit workout')
  await click('Done editing')
  let dialog = document.querySelector('dialog[open]')
  assert.ok(dialog)
  assert.match(dialog.textContent, /new active routine.*inactive version/)
  assert.equal(puts.length, 0)
  await click('Keep editing', dialog)
  assert.equal(document.querySelector('dialog'), null)
  assert.ok(button('Done editing'))
  assert.equal(document.querySelector('input[aria-label="Bench Press sets"]').value, '4')
  await click('Done editing')
  dialog = document.querySelector('dialog[open]')
  await click('Yes, update routine', dialog)
  assert.equal(puts.length, 1)
  assert.equal(puts[0].days[0].exercises[0].sets, 4)
  assert.equal(puts[0].days[0].exercises[0].exercise_id, 1)
  assert.equal(button('Saving routine…', dialog).disabled, true)
  await act(async () => {
    dialog.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))
    dialog.dispatchEvent(new window.Event('cancel', { cancelable: true }))
  })
  assert.equal(puts.length, 1)
  assert.ok(document.querySelector('dialog[open]'))
  await act(async () => finishSave())
  assert.equal(document.querySelector('dialog'), null)
  assert.ok(button('Edit workout'))
  assert.match(document.querySelector('.save-message').textContent, /Routine updated and selected as your active routine/)
  await click('My Routine')
  assert.equal(document.querySelector('input[aria-label="Bench Press sets"]').value, '4')
})

test('failed updates keep the disclaimer and edited values available for retry', async (context) => {
  let attempts = 0
  context.mock.method(globalThis, 'fetch', async (_url, options) => {
    if (options.method !== 'PUT') return routineResponse(plan)
    attempts += 1
    return attempts === 1
      ? Response.json({ detail: 'Could not write routine.' }, { status: 500 })
      : routineResponse(JSON.parse(options.body))
  })
  await click('My Routine')
  await changeSets('5')
  await click('Edit workout')
  await click('Done editing')
  await click('Yes, update routine', document.querySelector('dialog'))
  assert.match(document.querySelector('dialog [role="alert"]').textContent, /HTTP 500.*Could not write routine/)
  assert.equal(document.querySelector('input[aria-label="Bench Press sets"]').value, '5')
  assert.equal(button('Yes, update routine', document.querySelector('dialog')).disabled, false)
  await click('Yes, update routine', document.querySelector('dialog'))
  assert.equal(attempts, 2)
  assert.equal(document.querySelector('dialog'), null)
})

test('invalid targets do not open a save confirmation or issue PUT', async (context) => {
  const fetch = context.mock.method(globalThis, 'fetch', async () => routineResponse(plan))
  await click('My Routine')
  await click('Edit workout')
  await changeSets('0')
  await click('Done editing')
  assert.equal(document.querySelector('dialog'), null)
  assert.match(document.querySelector('[role="alert"]').textContent, /Enter 1.20 sets/)
  assert.equal(fetch.mock.callCount(), 1)
})

test('suggested additions retain catalog IDs and custom swaps cannot save under the previous ID', async (context) => {
  const source = structuredClone(plan)
  source.days[0].exercises = [plan.days[0].exercises[0]]
  source.days.push({
    ...source.days[0], day: 2, day_type: 'Shoulders',
    exercises: [plan.days[0].exercises[1]],
  })
  const puts = []
  context.mock.method(globalThis, 'fetch', async (_url, options) => {
    if (options.method !== 'PUT') return routineResponse(source)
    const payload = JSON.parse(options.body)
    puts.push(payload)
    return routineResponse(payload)
  })
  await click('My Routine')
  await click('Edit workout')
  await click('Add exercise to Push')
  let dialog = document.querySelector('dialog[open]')
  dialog.querySelector('input[name="name"]').value = 'Overhead Press'
  await click('Add exercise', dialog)
  await click('Done editing')
  await click('Yes, update routine', document.querySelector('dialog'))
  assert.equal(puts.length, 1)
  assert.deepEqual(puts[0].days[0].exercises.map((exercise) => exercise.exercise_id), [1, 2])
  assert.equal(puts[0].days[0].exercises[1].notes, '')
  await click('Edit workout')
  await act(async () => document.querySelector('[aria-label="Swap Bench Press"]').click())
  dialog = document.querySelector('dialog[open]')
  dialog.querySelector('input[name="name"]').value = 'Custom press'
  await click('Swap exercise', dialog)
  await click('Done editing')
  await click('Yes, update routine', document.querySelector('dialog'))
  assert.match(document.querySelector('dialog [role="alert"]').textContent, /Custom exercises cannot be saved/)
  assert.equal(puts.length, 1)
  assert.equal(document.querySelector('input[aria-label="Custom press sets"]').value, '3')
})

  function twoDayPlan() {
    const source = structuredClone(plan)
    source.days.push({
      ...source.days[0], day: 2, day_type: 'Pull',
      exercises: [{ ...source.days[0].exercises[1], name: 'Row' }],
    })
    return source
  }

  async function markDone(name) {
    await act(async () => document.querySelector(`[aria-label="Mark ${name} complete"]`).click())
  }

  async function fillBenchSets(scope = document) {
    for (let number = 1; number <= 3; number += 1) {
      await changeInput(`Bench Press set ${number} reps`, String(11 - number), scope)
      await changeInput(`Bench Press set ${number} weight`, String(40 + number / 2), scope)
    }
  }

  function workoutResponse(payload, trainingId = 'workout-session-id') {
    return Response.json({
      training_id: trainingId, user_id: 7, routine_id: payload.routine_id,
      date: '2026-10-15', created_at: '2026-10-15T15:00:00Z', sets_saved: payload.sets.length,
    })
  }

  test('active workouts lock mouse and keyboard day switching; confirmation posts completed actual sets once', async (context) => {
    const posts = []
    let finishSave
    context.mock.method(globalThis, 'fetch', async (url, options) => {
      if (url.endsWith('/routine')) return routineResponse(twoDayPlan())
      assert.equal(url, '/api/users/7/workouts')
      assert.equal(options.method, 'POST')
      const payload = JSON.parse(options.body)
      posts.push(payload)
      return new Promise((resolve) => { finishSave = () => resolve(workoutResponse(payload)) })
    })
    await click('My Routine')
    assert.equal(document.querySelector('.workout-exercise-sets'), null)
    await click('Start Workout')
    assert.equal(document.querySelectorAll('.workout-exercise-sets fieldset').length, 5)
    assert.equal(document.querySelector('[aria-label="Bench Press set 1 reps"]').value, '')
    assert.equal(document.querySelector('[aria-label="Overhead Press set 1 reps"]').value, '')
    assert.equal(document.querySelector('dialog'), null)
    let tabs = document.querySelectorAll('[role="tab"]')
    assert.equal(tabs[1].disabled, true)
    assert.equal(button('Edit workout').disabled, true)
    await act(async () => {
      tabs[1].click()
      tabs[0].dispatchEvent(new window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
      tabs[0].dispatchEvent(new window.KeyboardEvent('keydown', { key: 'End', bubbles: true }))
    })
    assert.equal(tabs[0].getAttribute('aria-selected'), 'true')
    await fillBenchSets()
    await markDone('Bench Press')
    await click('Finish workout')
    let dialog = document.querySelector('dialog[open]')
    assert.match(dialog.textContent, /Only filled sets from exercises marked Done/)
    assert.equal(dialog.querySelectorAll('input, fieldset').length, 0)
    assert.equal(posts.length, 0)
    await click('Keep working out', dialog)
    assert.equal(document.querySelector('dialog'), null)
    assert.ok(button('Finish workout'))
    assert.equal(tabs[1].disabled, true)
    assert.equal(document.querySelector('[aria-label="Bench Press set 2 reps"]').value, '9')
    await click('Finish workout')
    dialog = document.querySelector('dialog[open]')
    await click('Yes, finish and save', dialog)
    assert.equal(posts.length, 1)
    assert.deepEqual(posts[0], {
      routine_id: 42,
      sets: [
        { exercise_id: 1, reps: 10, weight: 40.5 },
        { exercise_id: 1, reps: 9, weight: 41 },
        { exercise_id: 1, reps: 8, weight: 41.5 },
      ],
    })
    assert.equal(button('Saving workout…', dialog).disabled, true)
    await act(async () => {
      dialog.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))
      dialog.dispatchEvent(new window.Event('cancel', { cancelable: true }))
    })
    assert.equal(posts.length, 1)
    assert.ok(document.querySelector('dialog[open]'))
    assert.equal(tabs[1].disabled, true)
    await act(async () => finishSave())
    assert.equal(document.querySelector('dialog'), null)
    assert.ok(button('Start Workout'))
    assert.match(document.querySelector('.routine-view').textContent, /Workout saved successfully/)
    tabs = document.querySelectorAll('[role="tab"]')
    assert.equal(tabs[1].disabled, false)
    await act(async () => tabs[1].click())
    assert.equal(tabs[1].getAttribute('aria-selected'), 'true')
  })

  test('workout save failure keeps actual entries, timer and day lock until a successful retry', async (context) => {
    const posts = []
    context.mock.method(globalThis, 'fetch', async (url, options) => {
      if (url.endsWith('/routine')) return routineResponse(twoDayPlan(), 58)
      const payload = JSON.parse(options.body)
      posts.push(payload)
      return posts.length === 1
        ? Response.json({ detail: 'Database unavailable.' }, { status: 500 })
        : workoutResponse(payload)
    })
    await click('My Routine')
    await click('Start Workout')
    await fillBenchSets()
    await markDone('Bench Press')
    await click('Finish workout')
    const dialog = document.querySelector('dialog[open]')
    await click('Yes, finish and save', dialog)
    assert.match(dialog.querySelector('[role="alert"]').textContent, /HTTP 500.*Database unavailable/)
    assert.equal(document.querySelector('input[aria-label="Bench Press set 2 reps"]').value, '9')
    assert.ok(document.querySelector('[aria-label="Elapsed time"]'))
    assert.equal(document.querySelectorAll('[role="tab"]')[1].disabled, true)
    await click('Yes, finish and save', dialog)
    assert.equal(posts.length, 2)
    assert.equal(posts[1].routine_id, 58)
    assert.deepEqual(posts[0], posts[1])
    assert.equal(document.querySelector('dialog'), null)
  })

  test('empty workouts and invalid actual values never POST or end the session', async (context) => {
    const fetch = context.mock.method(globalThis, 'fetch', async () => routineResponse(twoDayPlan()))
    await click('My Routine')
    await click('Start Workout')
    await click('Finish workout')
    let dialog = document.querySelector('dialog[open]')
    assert.match(dialog.textContent, /Enter reps for at least one set/)
    assert.equal(button('Yes, finish and save', dialog).disabled, true)
    await click('Keep working out', dialog)
    await markDone('Bench Press')
    assert.equal(button('Finish workout').disabled, true)
    await click('Finish workout')
    assert.equal(document.querySelector('dialog'), null)
    assert.match(document.querySelector('[role="alert"]').textContent, /Enter reps for at least one set/)
    await fillBenchSets()
    await changeInput('Bench Press set 2 weight', '-1')
    assert.equal(button('Finish workout').disabled, true)
    await changeInput('Bench Press set 2 weight', '0')
    await changeInput('Bench Press set 1 reps', '1.5')
    assert.equal(button('Finish workout').disabled, true)
    await changeInput('Bench Press set 1 reps', '10')
    assert.equal(button('Finish workout').disabled, false)
    assert.equal(fetch.mock.callCount(), 1)
    assert.ok(button('Finish workout'))
    assert.equal(document.querySelectorAll('[role="tab"]')[1].disabled, true)
  })

  test('active day and timer survive visiting chat and reopening My Routine without reloading the plan', async (context) => {
    const fetch = context.mock.method(globalThis, 'fetch', async (url) => {
      if (url.endsWith('/days')) return Response.json(
        Array.from({ length: 7 }, (_, index) => ({
          date: `2026-10-${11 + index}`, day_of_week: '', has_routine: false,
        })),
      )
      return routineResponse(twoDayPlan())
    })
    await click('My Routine')
    await act(async () => document.querySelectorAll('[role="tab"]')[1].click())
    await click('Start Workout')
    await changeInput('Row set 1 reps', '12')
    await changeInput('Row set 1 weight', '25.5')
    await changeInput('Row set 2 reps', '9')
    await markDone('Row')
    await click('AI Chat')
    await click('My Routine')
    const tabs = document.querySelectorAll('[role="tab"]')
    assert.equal(tabs[1].getAttribute('aria-selected'), 'true')
    assert.equal(tabs[0].disabled, true)
    assert.ok(button('Finish workout'))
    assert.ok(document.querySelector('[aria-label="Elapsed time"]'))
    assert.equal(document.querySelector('[aria-label="Mark Row incomplete"]').getAttribute('aria-checked'), 'true')
    assert.equal(document.querySelector('[aria-label="Row set 1 reps"]').value, '12')
    assert.equal(document.querySelector('[aria-label="Row set 1 weight"]').value, '25.5')
    assert.equal(document.querySelector('[aria-label="Row set 2 reps"]').value, '9')
    assert.equal(fetch.mock.calls.filter(({ arguments: [url] }) => url.endsWith('/routine')).length, 1)
    assert.equal(fetch.mock.calls.filter(({ arguments: [url] }) => url.endsWith('/days')).length, 1)
  })

test('missing routine identity is an explicit load error rather than saving against a guessed ID', async (context) => {
  context.mock.method(globalThis, 'fetch', async () => Response.json(plan))
  await click('My Routine')
  assert.match(document.querySelector('[role="alert"]').textContent, /no valid routine ID/)
  assert.equal(document.querySelector('.start-workout'), null)
})

test('saving skips blank sets and empty completed exercises, allowing optional blank weights', async (context) => {
  const posts = []
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url.endsWith('/routine')) return routineResponse(plan)
    const payload = JSON.parse(options.body)
    posts.push(payload)
    return workoutResponse(payload)
  })
  await click('My Routine')
  await click('Start Workout')
  await changeInput('Bench Press set 1 reps', '10')
  await changeInput('Bench Press set 1 weight', '')
  await changeInput('Bench Press set 2 weight', '40')
  await changeInput('Bench Press set 3 reps', '8')
  await changeInput('Bench Press set 3 weight', '35.5')
  await markDone('Bench Press')
  await markDone('Overhead Press')
  assert.equal(button('Finish workout').disabled, false)
  assert.equal(document.querySelector('[role="alert"]'), null)
  await click('Finish workout')
  await click('Yes, finish and save', document.querySelector('dialog'))
  assert.equal(posts.length, 1)
  assert.deepEqual(posts[0], {
    routine_id: 42,
    sets: [
      { exercise_id: 1, reps: 10, weight: null },
      { exercise_id: 1, reps: 8, weight: 35.5 },
    ],
  })
  assert.ok(button('Start Workout'))
})

test('workouts after routine edits use the new routine version ID', async (context) => {
  const posts = []
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    if (options.method === 'PUT') return routineResponse(JSON.parse(options.body), 99)
    if (url.endsWith('/routine')) return routineResponse(plan)
    const payload = JSON.parse(options.body)
    posts.push(payload)
    return workoutResponse(payload)
  })
  await click('My Routine')
  await click('Edit workout')
  await click('Done editing')
  await click('Yes, update routine', document.querySelector('dialog'))
  await click('Start Workout')
  await fillBenchSets()
  await markDone('Bench Press')
  await click('Finish workout')
  const dialog = document.querySelector('dialog')
  await click('Yes, finish and save', dialog)
  assert.equal(posts.length, 1)
  assert.equal(posts[0].routine_id, 99)
  await click('Start Workout')
  assert.equal(document.querySelector('[aria-label="Mark Bench Press complete"]').getAttribute('aria-checked'), 'false')
  assert.equal(document.querySelector('[aria-label="Bench Press set 1 reps"]').value, '')
})

test('a delayed chat routine save cannot replace a workout that started while the request was pending', async (context) => {
  let finishChat
  context.mock.method(globalThis, 'fetch', async (url) => {
    if (url.endsWith('/routine')) return routineResponse(twoDayPlan())
    assert.ok(url.endsWith('/chat'))
    return new Promise((resolve) => { finishChat = resolve })
  })
  await act(async () => {
    const input = document.querySelector('textarea')
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(input, 'Save a new routine')
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
  await act(async () => {
    document.querySelector('.composer').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))
  })
  await click('My Routine')
  await click('Start Workout')
  await markDone('Bench Press')
  await act(async () => finishChat(Response.json({
    subsystem: 'routine_maker',
    response: {
      status: 'saved', message: 'Saved.', routine_id: 99,
      routine: { ...plan, name: 'A newer routine' },
    },
  })))
  assert.ok(button('Finish workout'))
  assert.equal(document.querySelectorAll('[role="tab"]')[1].disabled, true)
  assert.match(document.querySelector('.routine-view h1').textContent, /Saved plan/)
  assert.equal(document.querySelector('[aria-label="Mark Bench Press incomplete"]').getAttribute('aria-checked'), 'true')
})
