/**
 * @file Cross-feature localization and frontend-contract regression suite.
 * Vite-loaded application modules are exercised with static rendering and isolated
 * happy-dom roots. Mocked APIs cover specialist validation/rendering, routine
 * confirmation, profile activation, theme persistence, and translated recovery UI.
 */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { after, before, test, mock } from 'node:test'
import { act, createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Window } from 'happy-dom'
import { createServer } from 'vite'

let server
let translations
let chat
let MainView
let RoutineView
let FailingView
let ThemeContext
let SubsystemResponse
let exerciseData
let usersApi
let routineData
let workoutEditing
let sessionTime
let reportData
let demoAnalysis
const storage = new Map()
const html = { lang: 'en' }
const originals = ['document', 'localStorage'].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)])

before(async () => {
  mock.method(globalThis, 'fetch', async () => { throw new Error('Unexpected network request in test') })
  mock.getter(navigator, 'language', () => 'es-ES')
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { documentElement: html } })
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  } })
  server = await createServer({ server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom' })
  translations = await server.ssrLoadModule('/src/i18n/index.jsx')
  chat = await server.ssrLoadModule('/src/features/ai-chat/api/chat.jsx')
  MainView = (await server.ssrLoadModule('/src/pages/MainView/MainView.jsx')).default
  RoutineView = (await server.ssrLoadModule('/src/components/RoutineView/RoutineView.jsx')).default
  FailingView = (await server.ssrLoadModule('/src/pages/FailingView/FailingView.jsx')).default
  ThemeContext = (await server.ssrLoadModule('/src/hooks/theme/ThemeContext.jsx')).ThemeContext
  SubsystemResponse = (await server.ssrLoadModule('/src/features/ai-chat/components/SubsystemResponse.jsx')).SubsystemResponse
  exerciseData = await server.ssrLoadModule('/src/features/ExplainerCard/exercise-data/exerciseData.jsx')
  usersApi = await server.ssrLoadModule('/src/hooks/session/users.js')
  routineData = await server.ssrLoadModule('/src/features/RoutineMaker/routine-data/routineData.js')
  workoutEditing = await server.ssrLoadModule('/src/features/RoutineView/workout-editing/workoutEditing.jsx')
  sessionTime = await server.ssrLoadModule('/src/features/RoutineView/workout-session/sessionTime.jsx')
  reportData = await server.ssrLoadModule('/src/features/PastRoutinesReport/report-data/reportData.js')
  demoAnalysis = await server.ssrLoadModule('/src/features/PastRoutinesReport/report-data/demoAnalysis.js')
})

after(async () => {
  await server?.close()
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
  }
  mock.restoreAll()
})

test('English and Spanish dictionaries have matching keys and placeholders', async () => {
  const en = JSON.parse(await readFile(new URL('./languages/en.json', import.meta.url), 'utf8'))
  const es = JSON.parse(await readFile(new URL('./languages/es.json', import.meta.url), 'utf8'))
  assert.deepEqual(Object.keys(en).sort(), Object.keys(es).sort())
  for (const key of Object.keys(en)) {
    if (Array.isArray(en[key])) {
      assert.equal(es[key].length, en[key].length, key)
    } else {
      assert.ok(es[key].trim(), key)
      assert.deepEqual(es[key].match(/{{[^}]+}}/g), en[key].match(/{{[^}]+}}/g), key)
    }
  }
})

test('Spanish browser locales select ES; saved preference takes priority and survives reinitialization', async () => {
  const { getInitialLanguage, setLanguage, languageStorageKey } = translations
  assert.equal(getInitialLanguage(), 'es')
  await setLanguage('en')
  assert.equal(storage.get(languageStorageKey), 'en')
  assert.equal(getInitialLanguage(), 'en')
  assert.equal(html.lang, 'en')
  await setLanguage('es')
  assert.equal(storage.get(languageStorageKey), 'es')
  assert.equal(getInitialLanguage(), 'es')
  assert.equal(html.lang, 'es')
  storage.delete(languageStorageKey)
  const language = mock.getter(navigator, 'language', () => 'fr-FR')
  assert.equal(getInitialLanguage(), 'en')
  language.mock.restore()
})

test('three subsystem suggestions populate localized questions and match the empty-chat shortcut', async () => {
  const window = new Window({ url: 'http://localhost' })
  const globals = {
    window, document: window.document, IS_REACT_ACT_ENVIRONMENT: true,
    requestAnimationFrame: window.requestAnimationFrame.bind(window),
  }
  const descriptors = Object.keys(globals).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)])
  for (const [key, value] of Object.entries(globals)) {
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  }
  const fetch = mock.method(globalThis, 'fetch', async (url) => {
    if (url.endsWith('/routine')) return Response.json(null)
    if (url.endsWith('/days')) return Response.json([])
    throw new Error(`Unexpected network request: ${url}`)
  })
  const { createRoot } = await import('react-dom/client')
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  const questions = {
    en: [
      'Create a 3-day gym routine to build muscle for an intermediate lifter, with 1 hour per session.',
      'Explain how to do a barbell deadlift, which muscles it works, and common mistakes to avoid.',
      'Analyze my saved workouts from the last 7 days and summarize my consistency, training volume, and progress.',
    ],
    es: [
      'Crea una rutina de gimnasio de 3 días para ganar masa muscular, de nivel intermedio y con 1 hora por sesión.',
      'Explícame cómo hacer un peso muerto con barra, qué músculos trabaja y qué errores comunes debo evitar.',
      'Analiza mis entrenamientos guardados de los últimos 7 días y resume mi constancia, volumen de entrenamiento y progreso.',
    ],
  }
  try {
    for (const language of ['en', 'es']) {
      await act(async () => {
        await translations.setLanguage(language)
        root.render(createElement(ThemeContext.Provider, {
          value: { theme: 'light', resolvedTheme: 'light', setTheme: () => {} },
        }, createElement(MainView, { user: { id: 1, username: 'Jamie Davis' }, onSwitchUser: () => {} })))
      })
      const buttons = [...container.querySelectorAll('.suggestions button')]
      assert.equal(buttons.length, 3)
      for (const [index, button] of buttons.entries()) {
        await act(async () => button.click())
        assert.equal(container.querySelector('textarea').value, questions[language][index])
      }
      await act(async () => container.querySelector('.empty-chat button').click())
      assert.equal(container.querySelector('textarea').value, questions[language][0])
    }
  } finally {
    await act(async () => root.unmount())
    fetch.mock.restore()
    window.close()
    for (const [key, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
})

test('storage failure is surfaced while the in-memory language still changes', async () => {
  const setter = mock.method(localStorage, 'setItem', () => { throw new Error('Storage denied') })
  await assert.rejects(translations.setLanguage('en'), /Storage denied/)
  assert.equal(translations.default.resolvedLanguage, 'en')
  assert.equal(html.lang, 'en')
  setter.mock.restore()
})

test('chat, routine and unavailable screens render in both languages without changing saved data', async () => {
  const before = structuredClone(chat.initialRoutine)
  for (const language of ['en', 'es']) {
    await translations.setLanguage(language)
    const main = renderToStaticMarkup(createElement(ThemeContext.Provider, {
      value: { theme: 'light', resolvedTheme: 'light', setTheme: () => {} },
    }, createElement(MainView, { user: { id: 1, username: 'Jamie Davis' }, onSwitchUser: () => {} })))
    assert.ok(main.includes(language === 'es' ? 'Crear mi rutina' : 'Build my routine'))
    assert.ok(main.includes(language === 'es' ? 'Enviar mensaje' : 'Send message'))
    assert.ok(main.includes(language === 'es' ? 'Claro' : 'Light'))
    assert.match(main, new RegExp(`lang="${language}"[^>]+aria-pressed="true"`))
    const routine = renderToStaticMarkup(createElement(RoutineView, { routine: chat.initialRoutine, workoutSession: { isWorkoutActive: false } }))
    assert.ok(routine.includes(language === 'es' ? 'Press de banca con barra' : 'Barbell bench press'))
    assert.ok(routine.includes(language === 'es' ? 'Editar entrenamiento' : 'Edit workout'))
    assert.ok(routine.includes(language === 'es' ? 'Iniciar entrenamiento' : 'Start Workout'))
    assert.ok(routine.includes(language === 'es' ? '0/5 completados' : '0/5 completed'))
    assert.equal((routine.match(/class="exercise-input"/g) || []).length, 15)
    assert.equal((routine.match(/role="checkbox"/g) || []).length, 5)
    assert.ok(!routine.includes('readonly') && !routine.includes('class="routine-summary"'))
    assert.ok(!routine.includes('class="exercise-grip"') && !routine.includes('class="add-exercise"'))
    const unavailable = renderToStaticMarkup(createElement(FailingView))
    assert.ok(unavailable.includes(language === 'es' ? 'Servidor no disponible' : 'Backend unavailable'))
    assert.ok(!main.includes('{{') && !routine.includes('{{'))
  }
  assert.deepEqual(chat.initialRoutine, before)
})

test('routine inputs accept rep ranges and fractional weights and reject invalid targets', () => {
  const { isValidExercise, isValidExerciseField } = workoutEditing
  const exercise = { sets: 3, reps: '8–12', weight: 0 }
  assert.equal(isValidExercise(exercise), true)
  for (const sets of [1, 20, '4']) assert.equal(isValidExercise({ ...exercise, sets }), true)
  for (const sets of ['', 0, 21, 1.5, 'oops']) assert.equal(isValidExercise({ ...exercise, sets }), false)
  for (const weight of [0, '0', 12.75, '100.25']) assert.equal(isValidExercise({ ...exercise, weight }), true)
  for (const weight of ['', ' ', -1, Infinity, 'oops', null, undefined]) assert.equal(isValidExercise({ ...exercise, weight }), false)
  for (const reps of ['8-12', 'AMRAP', '30s']) assert.equal(isValidExerciseField('reps', reps), true)
  for (const reps of ['', '   ', undefined]) assert.equal(isValidExerciseField('reps', reps), false)
})

test('exercise updates and reordering preserve prescriptions, completion, and other days', () => {
  const { updateDayExercises, moveExercise } = workoutEditing
  const before = structuredClone(chat.initialRoutine)
  const source = structuredClone(before)
  source.days[0].exercises[0].completed = true
  const next = updateDayExercises(source, 0, (exercises) => moveExercise(exercises, 0, 4))
  assert.deepEqual(next.days[0].exercises[4], source.days[0].exercises[0])
  assert.equal(next.days[1], source.days[1])
  assert.equal(next.days[0].exercises[0], source.days[0].exercises[1])
  assert.equal(source.days[0].exercises[0].name, before.days[0].exercises[0].name)
  for (const [from, to] of [[-1, 1], [0, 99], [null, 1], [1, 1]]) {
    assert.equal(moveExercise(source.days[0].exercises, from, to), source.days[0].exercises)
  }
  const empty = updateDayExercises(source, 0, () => [])
  assert.equal(empty.days[0].exercises.length, 0)
  const added = updateDayExercises(empty, 0, (exercises) => [...exercises, before.days[0].exercises[0]])
  assert.deepEqual(added.days[0].exercises, [before.days[0].exercises[0]])
  assert.deepEqual(chat.initialRoutine, before)
})

test('rest durations use the exact saved or demo prescription and timer formatting never goes negative', () => {
  const { restSeconds, formatTime } = sessionTime
  for (const [rest, seconds] of [['90s', 90], ['60s', 60], ['90 sec', 90], ['2 min', 120], ['1.5 minutes', 90], ['0s', 0]]) {
    assert.equal(restSeconds(rest), seconds)
  }
  for (const rest of ['oops', '-5s', '', '90', null]) assert.throws(() => restSeconds(rest), /Invalid rest duration/)
  for (const [seconds, time] of [[0, '00:00'], [9, '00:09'], [60, '01:00'], [125, '02:05'], [3600, '60:00'], [-1, '00:00']]) {
    assert.equal(formatTime(seconds), time)
  }
})

test('zero weights invite entry and every day card reports its own completion', async () => {
  await translations.setLanguage('en')
  const routine = structuredClone(chat.initialRoutine)
  routine.days[0].exercises[0].weight = 0
  routine.days[1].exercises[0].completed = true
  const rendered = renderToStaticMarkup(createElement(RoutineView, { routine, workoutSession: { isWorkoutActive: false } }))
  assert.match(rendered, /placeholder="-- kg" value=""/)
  assert.match(rendered, /1\/5 completed/)
  assert.equal((rendered.match(/aria-checked="false"/g) || []).length, 5)
  assert.ok(!rendered.includes('class="session-status"') && !rendered.includes('class="rest-countdown"'))
})

test('each chat request sends the exact uppercase language and preserves its response', async () => {
  for (const language of ['ES', 'EN']) {
    const calls = []
    const fetch = mock.method(globalThis, 'fetch', async (url, options) => {
      calls.push({ url, options })
      return Response.json({ subsystem: 'no_system', response: `Answer in ${language}` })
    })

    const result = await chat.requestChat('My question', 'test session', new AbortController().signal, language)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, '/api/test%20session/chat')
    assert.deepEqual(JSON.parse(calls[0].options.body), { query: 'My question', language })
    assert.equal(calls[0].options.method, 'POST')
    assert.deepEqual(result, { subsystem: 'no_system', content: `Answer in ${language}` })
    fetch.mock.restore()
  }
  await assert.rejects(chat.requestChat('Question', 'session', new AbortController().signal, 'es'), /EN or ES/)
})

test('routine drafts render structured days but only saved versions provide a recommendation for automatic storage', async () => {
  const routine = {
    name: 'PPL', recovery: 'Rest between days.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: 'Control each rep.' }],
    }],
  }
  for (const status of ['awaiting_confirmation', 'saved', 'needs_changes']) {
    const fetch = mock.method(globalThis, 'fetch', async (_url, options) => {
      assert.equal(JSON.parse(options.body).user_id, 7)
      return Response.json({
        subsystem: 'routine_maker',
        response: { status, message: 'Review this routine.', routine, routine_id: status === 'saved' ? 5 : null, draft_id: status === 'awaiting_confirmation' ? 'preview-1' : null },
      })
    })
    try {
      const result = await chat.requestChat('Make a routine', 'session', new AbortController().signal, 'EN', 7)
      if (status === 'saved') {
        assert.equal(result.content, 'Review this routine.')
        assert.deepEqual(result.savedRoutine, { id: 5, name: 'PPL' })
      } else {
        assert.equal(result.content, 'Review this routine.')
        assert.equal(result.savedRoutine, null)
      }
      assert.deepEqual(result.routine, routine)
      assert.equal(result.awaitingConfirmation, status === 'awaiting_confirmation')
      assert.equal(result.draftId, status === 'awaiting_confirmation' ? 'preview-1' : null)
      assert.equal(fetch.mock.callCount(), 1)
    } finally {
      fetch.mock.restore()
    }
  }
})

test('direct routine save puts the entire preview with its user and draft scope without a chat query', async () => {
  const routine = {
    name: 'Push', recovery: 'Rest.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  for (const language of ['EN', 'ES']) {
    const fetch = mock.method(globalThis, 'fetch', async (url, options) => {
      const parsed = new URL(url, 'http://localhost')
      assert.equal(parsed.pathname, '/api/users/7/routine')
      assert.deepEqual(Object.fromEntries(parsed.searchParams), {
        session_id: 'test session', draft_id: 'draft-1', language,
      })
      assert.equal(options.method, 'PUT')
      assert.equal(options.headers['Content-Type'], 'application/json')
      assert.deepEqual(JSON.parse(options.body), routine)
      return Response.json(routine)
    })
    try {
      const result = await chat.requestRoutineSave('test session', routine, 'draft-1', new AbortController().signal, language, 7)
      assert.equal(result.awaitingConfirmation, false)
      assert.ok(result.content.includes(language === 'ES' ? 'Guardada' : 'Saved'))
      assert.deepEqual(result.savedRoutine, { name: 'Push' })
      assert.deepEqual(result.routine, routine)
      assert.equal(fetch.mock.callCount(), 1)
    } finally {
      fetch.mock.restore()
    }
  }
})

test('routine JSON renders localized metadata, day tabs and exercise tables instead of a Markdown plan', async () => {
  for (const language of ['en', 'es']) {
    await translations.setLanguage(language)
    for (const count of [1, 3, 7]) {
      const routine = {
        name: 'Balanced week', summary: 'A manageable split with recovery between sessions.',
        recovery: 'Rest between training days.',
        days: Array.from({ length: count }, (_, index) => ({
          day: index + 1, day_type: `Focus ${index + 1}`, info: 'Warm up first.',
          duration_minutes: 30 + index * 5,
          exercises: [{
            exercise_id: 901, name: 'Catalog Press', sets: 4, reps: '8-12', rest_seconds: 90,
            notes: 'Use controlled movements.',
          }],
        })),
      }
      const fetch = mock.method(globalThis, 'fetch', async () => Response.json({
        subsystem: 'routine_maker',
        response: { status: 'awaiting_confirmation', message: 'Review your draft.', routine, draft_id: 'preview', routine_id: null },
      }))
      try {
        const result = await chat.requestChat('Create a plan', 'session', new AbortController().signal, language.toUpperCase(), 7)
        assert.deepEqual(result.routine, routine)
        assert.equal(result.content, 'Review your draft.')
        const markup = renderToStaticMarkup(createElement(SubsystemResponse, { ...result, onExplainExercise: () => {} }))
        assert.match(markup, /class="routine-maker"/)
        assert.equal((markup.match(/role="tab"/g) || []).length, count)
        assert.equal((markup.match(/aria-selected="true"/g) || []).length, 1)
        assert.match(markup, /role="tabpanel"/)
        assert.match(markup, /<table role="table">/)
        for (const [label, value] of [['SETS', '4'], ['REPS', '8-12'], ['Rest', '90s']]) {
          assert.ok(markup.includes(`<td role="cell"><span class="routine-maker-cell-label">${translations.default.t(label)}</span>${value}</td>`))
        }
        assert.ok(markup.includes(language === 'es' ? 'Días de entrenamiento' : 'Training days'))
        assert.ok(markup.includes(language === 'es' ? 'Explicar Catalog Press' : 'Explain Catalog Press'))
        assert.equal(markup.split(routine.summary).length - 1, 1)
        assert.ok(!markup.includes('901') && !markup.includes('KG') && !markup.includes('DONE'))
        assert.ok(!markup.includes('## Balanced week') && !markup.includes('[object Object]'))
        const restored = routineData.toWorkoutRoutine(result.routine)
        const myRoutine = renderToStaticMarkup(createElement(RoutineView, { routine: restored, workoutSession: { isWorkoutActive: false } }))
        assert.match(myRoutine, /class="routine-view"/)
        assert.match(myRoutine, /class="workout-card"/)
        assert.ok(!myRoutine.includes('class="routine-maker"'))
        assert.ok(!myRoutine.includes('Demo workout') && !myRoutine.includes('Entrenamiento de ejemplo'))
        assert.equal((myRoutine.match(/role="tab"/g) || []).length, count)
        assert.ok(myRoutine.includes('Catalog Press'))
        assert.ok(myRoutine.includes('Use controlled movements.'))
        assert.ok(myRoutine.includes('Rest between training days.'))
        assert.ok(myRoutine.includes(routine.summary))
        assert.deepEqual(restored.days[0].exercises[0], {
          exerciseId: 901, name: 'Catalog Press', sets: 4, reps: '8-12', rest: '90s',
          notes: 'Use controlled movements.', weight: 0, completed: false,
        })
      } finally {
        fetch.mock.restore()
      }
    }
  }
})

test('past routine analyses render the explanation with a route-specific visual report', async () => {
  const cases = [
    ['Show my last pull day', 'past_day_exercise', /class="set-list"/, { en: 'Exercise breakdown', es: 'Desglose por ejercicio' }],
    ['Compare my last two push days', 'compare_last_two_workouts', /class="diverging-chart"/, { en: 'Strengths &amp; weaknesses', es: 'Fortalezas y debilidades' }],
    ['How was my week?', 'weekly_performance', /class="radar-chart"/, { en: 'Heaviest lift of the week', es: 'Levantamiento más pesado de la semana' }],
  ]
  for (const language of ['en', 'es']) {
    await translations.setLanguage(language)
    for (const [query, route, chart, heading] of cases) {
      const analysis = demoAnalysis.demoPastRoutinesAnalysis(query)
      assert.equal(analysis.route, route)
      const fetch = mock.method(globalThis, 'fetch', async (_url, options) => {
        assert.deepEqual(JSON.parse(options.body), { query, language: language.toUpperCase(), user_id: 2, client_saves_routine: true })
        return Response.json({ subsystem: 'past_routines_analyzer', response: analysis })
      })
      try {
        const result = await chat.requestChat(query, 'session', new AbortController().signal, language.toUpperCase(), 2)
        assert.equal(result.content, analysis.llm_explain)
        assert.deepEqual(result.analysis, analysis)
        const markup = renderToStaticMarkup(createElement(SubsystemResponse, { ...result, onExplainExercise: () => {} }))
        assert.match(markup, /class="routines-report"/)
        assert.match(markup, chart)
        assert.ok(markup.includes(heading[language]), `${route} ${language}`)
        assert.ok(markup.includes('demo data'))
        assert.ok(!markup.includes('[object Object]') && !markup.includes('NaN'))
      } finally {
        fetch.mock.restore()
      }
    }
  }
  const empty = renderToStaticMarkup(createElement(SubsystemResponse, {
    subsystem: 'past_routines_analyzer', content: 'Nothing yet.',
    analysis: { route: 'weekly_performance', day_type: null, data: [], llm_explain: 'Nothing yet.' },
  }))
  assert.match(empty, /class="report-empty"/)
})

test('past routine responses are validated and comparison helpers find strengths and weaknesses', async () => {
  for (const response of [
    { route: 'unknown', day_type: null, data: [], llm_explain: 'Text' },
    { route: 'weekly_performance', day_type: null, data: [], llm_explain: ' ' },
    { route: 'past_day_exercise', day_type: 'push', data: [{ nested: {} }], llm_explain: 'Text' },
    { route: 'past_day_exercise', day_type: 'push', data: null, llm_explain: 'Text' },
  ]) {
    const fetch = mock.method(globalThis, 'fetch', async () => Response.json({ subsystem: 'past_routines_analyzer', response }))
    try {
      await assert.rejects(chat.requestChat('History', 'session', new AbortController().signal, 'EN', 2), /invalid response/)
    } finally {
      fetch.mock.restore()
    }
  }
  /**
   * Creates paired-session measurements for loaded/bodyweight metric assertions.
   * @param {number} rank - Latest (1) or previous (2) session.
   * @param {string} name - Exercise identity.
   * @param {number} reps - Actual repetitions.
   * @param {number} weight - Actual external load.
   * @returns {object} Scalar history row.
   */
  const row = (rank, name, reps, weight) => ({ training_rank: rank, exercise_name: name, exercise_order: 1, set_number: 1, reps, weight, primary_muscle: 'chest' })
  const comparison = reportData.compareWorkouts([
    row(1, 'Bench', 8, 80), row(2, 'Bench', 8, 70),
    row(1, 'Dips', 8, 0), row(2, 'Dips', 10, 0),
    row(1, 'Fly', 10, 20),
  ])
  assert.deepEqual(comparison.strengths.map((item) => item.name), ['Bench'])
  assert.deepEqual(comparison.weaknesses.map((item) => item.name), ['Dips'])
  assert.equal(comparison.weaknesses[0].change, -0.2)
  assert.equal(comparison.exercises.find((item) => item.name === 'Fly').change, null)
  assert.equal(comparison.latest.volume, 80 * 8 + 20 * 10)
  assert.equal(reportData.estimatedOneRepMax({ reps: 1, weight: 100 }), 100)
  assert.equal(reportData.estimatedOneRepMax({ reps: 10, weight: 0 }), 0)
})

test('routine JSON rejects malformed days, duplicate exercises and invalid targets', () => {
  const routine = {
    name: 'Push', recovery: 'Rest.', days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  assert.equal(routineData.isRoutinePlan(routine), true)
  for (const update of [
    (plan) => { plan.days = [] },
    (plan) => { plan.days[0] = null },
    (plan) => { plan.days[0].day = 2 },
    (plan) => { plan.days[0].duration_minutes = -1 },
    (plan) => { plan.days[0].exercises.push({ ...plan.days[0].exercises[0] }) },
    (plan) => { plan.days[0].exercises[0] = null },
    (plan) => { plan.days[0].exercises[0].sets = 0 },
    (plan) => { plan.days[0].exercises[0].reps = '' },
    (plan) => { plan.days[0].exercises[0].rest_seconds = 901 },
    (plan) => { plan.summary = 'x'.repeat(601) },
  ]) {
    const invalid = structuredClone(routine)
    update(invalid)
    assert.equal(routineData.isRoutinePlan(invalid), false)
  }
})

test('legacy routine timing stays unknown and cannot be saved as a complete plan', () => {
  const legacy = {
    storage_format: 'legacy', name: 'Saved templates', summary: '', recovery: 'Not recorded.',
    days: [{
      day: 1, routine_id: 9, day_type: 'Push', info: 'Pressing.', duration_minutes: null,
      exercises: [{ exercise_id: 1, name: 'Press', sets: 2, reps: '8', rest_seconds: null, notes: '' }],
    }],
  }
  assert.equal(routineData.isSavedRoutinePlan(legacy), true)
  assert.equal(routineData.isRoutinePlan(legacy), false)
  const workout = routineData.toWorkoutRoutine(legacy)
  assert.equal(workout.storageFormat, 'legacy')
  assert.equal(workout.days[0].routineId, 9)
  assert.equal(workout.days[0].durationMinutes, null)
  assert.equal(workout.days[0].exercises[0].rest, null)
  assert.throws(() => routineData.toRoutinePlan(workout), /read-only/)
  const invalid = structuredClone(legacy)
  invalid.days[0].routine_id = null
  assert.equal(routineData.isSavedRoutinePlan(invalid), false)
})

test('My Routine does not render device-only routine data as the saved plan', async () => {
  await translations.setLanguage('en')
  const routine = {
    name: 'Saved plan', summary: 'A short explanation.', recovery: 'Rest between days.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Catalog Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  const stored = { ...chat.initialRoutine, generated: routine }
  storage.set('form-routine-v1:77', JSON.stringify(stored))
  const markup = renderToStaticMarkup(createElement(ThemeContext.Provider, {
    value: { theme: 'light', resolvedTheme: 'light', setTheme: () => {} },
  }, createElement(MainView, { user: { id: 77, username: 'Test User' }, onSwitchUser: () => {} })))
  assert.ok(!markup.includes('A short explanation.'))
  assert.ok(!markup.includes('Could not restore your routine'))
  assert.deepEqual(JSON.parse(storage.get('form-routine-v1:77')), stored)
  storage.delete('form-routine-v1:77')
})

test('button and chat saves render the same localized confirmation without repeating the plan', async () => {
  const routine = {
    name: 'My saved plan', recovery: 'Rest between days.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  for (const language of ['en', 'es']) {
    await translations.setLanguage(language)
    const message = translations.default.getFixedT(language)('Saved as a new version and selected as your current routine.')
    const fetch = mock.method(globalThis, 'fetch', async (url, options) => {
      if (url.endsWith('/chat')) {
        assert.equal(JSON.parse(options.body).client_saves_routine, true)
        return Response.json({
          subsystem: 'routine_maker',
          response: { status: 'save_requested', message: 'Saving…', routine, routine_id: null, draft_id: 'draft' },
        })
      }
      assert.equal(options.method, 'PUT')
      assert.equal(new URL(url, 'http://localhost').pathname, '/api/users/7/routine')
      assert.deepEqual(JSON.parse(options.body), routine)
      return Response.json(routine)
    })
    try {
      const signal = new AbortController().signal
      const buttonSave = await chat.requestRoutineSave('session', routine, 'draft', signal, language.toUpperCase(), 7)
      const chatSave = await chat.requestChat('Save this routine', 'session', signal, language.toUpperCase(), 7)
      assert.equal(fetch.mock.callCount(), 3)
      /**
       * Renders normalized save replies to compare button and chat-confirmation UI.
       * @param {import('../features/ai-chat/api/chat').ChatResult} result - Saved-plan reply.
       * @returns {string} Static confirmation markup.
       */
      const render = (result) => renderToStaticMarkup(createElement(SubsystemResponse, result))
      const markup = render(buttonSave)
      assert.equal(markup, render(chatSave))
      assert.match(markup, /class="saved-routine"/)
      assert.ok(markup.includes(language === 'es' ? 'Rutina guardada' : 'Routine saved'))
      assert.ok(!markup.includes('42'))
      assert.equal(markup.split('My saved plan').length - 1, 1)
      assert.equal(markup.split(message).length - 1, 1)
      assert.equal((markup.match(/<button/g) || []).length, 0)
      assert.ok(!markup.includes('Bench Press') && !markup.includes('Rest between days.'))
      assert.deepEqual(buttonSave.routine, routine)
    } finally {
      fetch.mock.restore()
    }
  }
})

test('legacy saved chat responses still require a valid database ID', async () => {
  for (const routineId of [null, 0, '42']) {
    const fetch = mock.method(globalThis, 'fetch', async () => Response.json({
      subsystem: 'routine_maker',
      response: {
        status: 'saved', message: 'Saved.', routine_id: routineId,
        routine: {
          name: 'Push', recovery: 'Rest.',
          days: [{
            day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
            exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
          }],
        },
      },
    }))
    try {
      await translations.setLanguage('en')
      const signal = new AbortController().signal
      await assert.rejects(chat.requestChat('Save it', 'session', signal, 'EN', 7), /invalid response/)
    } finally {
      fetch.mock.restore()
    }
  }
})

test('direct save surfaces stale drafts and server failures without falling back to chat', async () => {
  const routine = {
    name: 'Push', recovery: 'Rest.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  for (const status of [422, 500]) {
    const fetch = mock.method(globalThis, 'fetch', async () => Response.json({
      detail: [{ msg: 'This draft is no longer available.' }],
    }, { status }))
    try {
      await assert.rejects(
        chat.requestRoutineSave('session', routine, 'old-draft', new AbortController().signal, 'EN', 7),
        new RegExp(`HTTP ${status}`),
      )
      assert.equal(fetch.mock.callCount(), 1)
    } finally {
      fetch.mock.restore()
    }
  }
})

test('chat save failures retain a retryable preview and never return a saved confirmation', async () => {
  const routine = {
    name: 'Push', recovery: 'Rest.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  const fetch = mock.method(globalThis, 'fetch', async (url) => {
    if (url.endsWith('/chat')) return Response.json({
      subsystem: 'routine_maker',
      response: { status: 'save_requested', message: 'Saving…', routine, draft_id: 'draft', routine_id: null },
    })
    return Response.json({ detail: 'Database unavailable' }, { status: 500 })
  })
  try {
    await assert.rejects(
      chat.requestChat('Save it', 'session', new AbortController().signal, 'EN', 7),
      (error) => {
        assert.match(error.message, /HTTP 500/)
        assert.equal(error.routineToSave.savedRoutine, null)
        assert.deepEqual(error.routineToSave.routine, routine)
        assert.equal(error.routineToSave.draftId, 'draft')
        return true
      },
    )
    assert.equal(fetch.mock.callCount(), 2)
  } finally {
    fetch.mock.restore()
  }
})

test('PUT save rejects invalid or empty responses without reporting success', async () => {
  const routine = {
    name: 'Push', recovery: 'Rest.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  for (const response of [null, {}, { routine }]) {
    const fetch = mock.method(globalThis, 'fetch', async () => Response.json(response))
    try {
      await assert.rejects(
        chat.requestRoutineSave('session', routine, 'draft', new AbortController().signal, 'EN', 7),
        /invalid routine/,
      )
    } finally {
      fetch.mock.restore()
    }
  }
})

test('routine responses reject invalid days and show user ownership errors with HTTP status', async () => {
  const fetch = mock.method(globalThis, 'fetch', async () => Response.json({
    subsystem: 'routine_maker',
    response: { status: 'awaiting_confirmation', message: 'Preview', routine: { name: 'Missing days' } },
  }))
  try {
    await assert.rejects(
      chat.requestChat('Routine', 'session', new AbortController().signal, 'EN', 1),
      /invalid response/,
    )
  } finally {
    fetch.mock.restore()
  }
  const validation = mock.method(globalThis, 'fetch', async () => Response.json({
    detail: [{ msg: 'Routine requests require user_id.' }],
  }, { status: 422 }))
  try {
    await assert.rejects(
      chat.requestChat('Routine', 'session', new AbortController().signal, 'EN'),
      /HTTP 422.*require user_id/,
    )
  } finally {
    validation.mock.restore()
  }
})

test('profile registration and every activation use the selected user ID and set-key endpoint', async () => {
  const calls = []
  const fetch = mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/users')) return Response.json({ id: 7, username: 'Alex', weight_unit: 'lbs' }, { status: 201 })
    if (url.endsWith('/chat')) return Response.json({ subsystem: 'no_system', response: 'Hello' })
    return Response.json({ id: url.includes('/7/') ? '7' : '1', created: true })
  })
  try {
    const signal = new AbortController().signal
    const user = await usersApi.registerUser(' Alex ', 'lbs', signal)
    assert.deepEqual(JSON.parse(calls[0].options.body), { username: 'Alex', weight_unit: 'lbs' })
    assert.equal(await usersApi.activateUser(user, signal), user)
    await usersApi.activateUser({ id: 1 }, signal)
    await usersApi.activateUser(user, signal)
    await chat.requestChat('Hi', '7', signal, 'EN', user.id)
    await usersApi.setSessionKey('7', signal, true)
    assert.deepEqual(calls.map(({ url }) => url), [
      '/api/users', '/api/7/key', '/api/1/key', '/api/7/key', '/api/7/chat', '/api/7/key?reset=true',
    ])
    assert.deepEqual(JSON.parse(calls[4].options.body), { query: 'Hi', language: 'EN', user_id: 7, client_saves_routine: true })
    assert.ok(calls.every(({ options }) => options.method === 'POST'))
  } finally {
    fetch.mock.restore()
  }
})

test('active routine fetch validates and returns the selected user’s saved plan', async () => {
  const routine = {
    name: 'Saved plan', recovery: 'Rest between days.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  const fetch = mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/users/7/routine')
    assert.equal(options.method, undefined)
    return Response.json(routine)
  })
  try {
    assert.deepEqual(await usersApi.getUserRoutine(7, new AbortController().signal), routine)
    fetch.mock.mockImplementation(async () => Response.json(null))
    assert.equal(await usersApi.getUserRoutine(7), null)
    await assert.rejects(usersApi.getUserRoutine(0), /positive integer/)
    fetch.mock.mockImplementation(async () => Response.json({ invalid: true }))
    await assert.rejects(usersApi.getUserRoutine(7), /invalid routine/)
  } finally {
    fetch.mock.restore()
  }
})

test('edited workout plans preserve catalog references and save through PUT without chat draft parameters', async () => {
  const plan = {
    name: 'Saved plan', summary: 'A balanced week.', recovery: 'Rest between days.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [
        { exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: 'Stay controlled.' },
        { exercise_id: 2, name: 'Overhead Press', sets: 2, reps: '10', rest_seconds: 60, notes: '' },
      ],
    }],
  }
  const original = structuredClone(plan)
  const workout = routineData.toWorkoutRoutine(plan)
  assert.equal(workout.days[0].exercises[0].exerciseId, 1)
  assert.deepEqual(routineData.toRoutinePlan(workout), plan)
  workout.days[0].exercises.reverse()
  workout.days[0].exercises[0].sets = '4'
  workout.days[0].exercises[0].weight = 12.5
  workout.days[0].exercises[0].completed = true
  const edited = routineData.toRoutinePlan(workout)
  assert.deepEqual(edited.days[0].exercises.map((exercise) => exercise.exercise_id), [2, 1])
  assert.equal(edited.days[0].exercises[0].sets, 4)
  assert.ok(!JSON.stringify(edited).includes('weight') && !JSON.stringify(edited).includes('completed'))
  assert.deepEqual(plan, original)
  const fetch = mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/users/7/routine')
    assert.equal(options.method, 'PUT')
    assert.deepEqual(JSON.parse(options.body), edited)
    return Response.json(edited)
  })
  try {
    assert.deepEqual(await usersApi.saveUserRoutine(7, edited), edited)
    assert.equal(fetch.mock.callCount(), 1)
    workout.days[0].exercises[0].exerciseId = null
    assert.throws(() => routineData.toRoutinePlan(workout), /Custom exercises cannot be saved/)
    workout.days[0].exercises = []
    assert.throws(() => routineData.toRoutinePlan(workout), /Each day needs exercises/)
    workout.days[0].exercises = [
      routineData.toWorkoutRoutine(plan).days[0].exercises[0],
      routineData.toWorkoutRoutine(plan).days[0].exercises[0],
    ]
    assert.throws(() => routineData.toRoutinePlan(workout), /no duplicates/)
    assert.equal(fetch.mock.callCount(), 1)
  } finally {
    fetch.mock.restore()
  }
})

test('failed registration and activation reject rather than report success', async () => {
  const fetch = mock.method(globalThis, 'fetch', async () => new Response('', { status: 409 }))
  try {
    await assert.rejects(usersApi.registerUser('Alex', 'kg'), /already registered/)
    fetch.mock.mockImplementation(async () => new Response('', { status: 500 }))
    await assert.rejects(usersApi.activateUser({ id: 7 }), /HTTP 500/)
  } finally {
    fetch.mock.restore()
  }
})

test('switching language does not rewrite an in-flight request; next request uses the new language', async () => {
  await translations.setLanguage('es')
  let finish
  const languages = []
  const fetch = mock.method(globalThis, 'fetch', async (_url, options) => {
    languages.push(JSON.parse(options.body).language)
    if (languages.length === 1) await new Promise((resolve) => { finish = resolve })
    return Response.json({ subsystem: 'no_system', response: 'Original response' })
  })
  const pending = chat.requestChat('First', 'session', new AbortController().signal,
    translations.default.resolvedLanguage.toUpperCase())
  await translations.setLanguage('en')
  finish()
  assert.equal((await pending).content, 'Original response')
  await chat.requestChat('Second', 'session', new AbortController().signal,
    translations.default.resolvedLanguage.toUpperCase())
  assert.deepEqual(languages, ['ES', 'EN'])
  fetch.mock.restore()
})

test('API errors are localized without hiding HTTP status or backend failures', async () => {
  for (const language of ['ES', 'EN']) {
    const fetch = mock.method(globalThis, 'fetch', async () => new Response('', { status: 422 }))
    await assert.rejects(
      chat.requestChat('Question', 'session', new AbortController().signal, language),
      language === 'ES' ? /ha devuelto HTTP 422/ : /returned HTTP 422/,
    )
    fetch.mock.restore()
  }
  const fetch = mock.method(globalThis, 'fetch', async () => { throw new TypeError('Offline') })
  await assert.rejects(chat.requestChat('Question', 'session', new AbortController().signal, 'ES'),
    (error) => error.backendDown === true && /conectar con el servidor/.test(error.message))
  fetch.mock.restore()
})

const explanation = {
  id: 1,
  name: 'Barbell Bench Press',
  description: 'Exact catalog description.',
  instructions: '1. Set your position.\n2. Lower with control.\n3. Press up.',
  icon_url: 'database/images/icon/bench-press-1.png',
  anatomy_diagram_url: 'database/images/anatomy/anatomy_chest_sec_shoulders.svg',
  media_urls: [
    'database/images/media/Barbell_Bench_Press_-_Medium_Grip/0.jpg',
    'database/images/media/Barbell_Bench_Press_-_Medium_Grip/1.jpg',
  ],
  llm_explanation: 'Your **personalized explanation**. Ask for clarification.',
}

test('explainer API responses preserve structured catalog fields and reject malformed exercises', async () => {
  for (const response of [
    [explanation],
    [explanation, { ...explanation, id: 2, description: null, media_urls: null, icon_url: null, anatomy_diagram_url: null }],
    'Which exercise would you like explained?',
  ]) {
    const fetch = mock.method(globalThis, 'fetch', async () => Response.json({ subsystem: 'exercise_explainer', response }))
    const result = await chat.requestChat('Explain', 'session', new AbortController().signal, 'EN')
    assert.deepEqual(result, { subsystem: 'exercise_explainer', content: response })
    fetch.mock.restore()
  }
  for (const response of [[], [{}], [{ ...explanation, media_urls: 'bad' }], [{ ...explanation, llm_explanation: null }]]) {
    const fetch = mock.method(globalThis, 'fetch', async () => Response.json({ subsystem: 'exercise_explainer', response }))
    await assert.rejects(chat.requestChat('Explain', 'session', new AbortController().signal, 'EN'), /invalid exercise list/)
    fetch.mock.restore()
  }
})

test('explainer cards render localized HTML, image URLs, multi-exercise controls and safe coach Markdown', async () => {
  for (const language of ['en', 'es']) {
    await translations.setLanguage(language)
    const markup = renderToStaticMarkup(createElement(SubsystemResponse, {
      subsystem: 'exercise_explainer', content: [explanation, { ...explanation, id: 2 }],
    }))
    assert.match(markup, /class="explainer-card"/)
    assert.match(markup, /1 \/ 2/)
    assert.match(markup, /<nav class="explainer-navigation"/)
    assert.match(markup, /<span>(Next exercise|Ejercicio siguiente)<\/span>/)
    assert.match(markup, /<strong>personalized explanation<\/strong>/)
    assert.match(markup, /src="\/api\/database\/images\/media\//)
    assert.ok(markup.includes(language === 'en' ? 'Next exercise' : 'Ejercicio siguiente'))
    assert.ok(markup.includes(language === 'en' ? 'Coach Insight' : 'Consejo del entrenador'))
    const single = renderToStaticMarkup(createElement(SubsystemResponse, {
      subsystem: 'exercise_explainer', content: [{ ...explanation, media_urls: null, anatomy_diagram_url: null }],
    }))
    assert.ok(!single.includes('explainer-navigation') && !single.includes('explainer-gallery'))
    const legacy = renderToStaticMarkup(createElement(SubsystemResponse, { subsystem: 'exercise_explainer', content: 'Clarification **question**' }))
    assert.match(legacy, /<strong>question<\/strong>/)
  }
})

test('exercise helpers parse steps and resolve only supported media paths', () => {
  assert.deepEqual(exerciseData.parseInstructions(explanation.instructions), [
    'Set your position.', 'Lower with control.', 'Press up.',
  ])
  assert.deepEqual(exerciseData.parseInstructions('1. Start. 2. Finish.'), ['Start.', 'Finish.'])
  assert.deepEqual(exerciseData.parseInstructions(['1. First', 'Second']), ['First', 'Second'])
  assert.equal(exerciseData.resolveExerciseAsset('/database/images/icon/example.png'), '/api/database/images/icon/example.png')
  assert.equal(exerciseData.resolveExerciseAsset('https://example.com/image.png'), 'https://example.com/image.png')
  assert.equal(exerciseData.resolveExerciseAsset('javascript:alert(1)'), null)
  assert.equal(exerciseData.resolveExerciseAsset(null), null)
})
