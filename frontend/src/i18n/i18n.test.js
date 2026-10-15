import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { after, before, test, mock } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
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
    const routine = renderToStaticMarkup(createElement(RoutineView, { routine: chat.initialRoutine }))
    assert.ok(routine.includes(language === 'es' ? 'Press de banca con barra' : 'Barbell bench press'))
    assert.ok(routine.includes(language === 'es' ? 'Editar entrenamiento' : 'Edit workout'))
    const unavailable = renderToStaticMarkup(createElement(FailingView))
    assert.ok(unavailable.includes(language === 'es' ? 'Servidor no disponible' : 'Backend unavailable'))
    assert.ok(!main.includes('{{') && !routine.includes('{{'))
  }
  assert.deepEqual(chat.initialRoutine, before)
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
    } finally {
      fetch.mock.restore()
    }
  }
})

test('direct routine save posts the draft identity without a chat query', async () => {
  const routine = {
    name: 'Push', recovery: 'Rest.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Bench Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  for (const language of ['EN', 'ES']) {
    const fetch = mock.method(globalThis, 'fetch', async (url, options) => {
      assert.equal(url, '/api/test%20session/routine/save')
      assert.equal(options.method, 'POST')
      assert.deepEqual(JSON.parse(options.body), { user_id: 7, draft_id: 'draft-1', language })
      return Response.json({
        subsystem: 'routine_maker',
        response: { status: 'saved', message: 'Saved.', routine, routine_id: 8, draft_id: null },
      })
    })
    try {
      const result = await chat.requestRoutineSave('test session', 'draft-1', new AbortController().signal, language, 7)
      assert.equal(result.routineId, 8)
      assert.equal(result.awaitingConfirmation, false)
      assert.equal(result.content, 'Saved.')
      assert.deepEqual(result.savedRoutine, { id: 8, name: 'Push' })
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
        assert.match(markup, /<table>/)
        assert.match(markup, /<td>4<\/td><td>8-12<\/td><td>90s<\/td>/)
        assert.ok(markup.includes(language === 'es' ? 'Días de entrenamiento' : 'Training days'))
        assert.ok(markup.includes(language === 'es' ? 'Explicar Catalog Press' : 'Explain Catalog Press'))
        assert.equal(markup.split(routine.summary).length - 1, 1)
        assert.ok(!markup.includes('901') && !markup.includes('KG') && !markup.includes('DONE'))
        assert.ok(!markup.includes('## Balanced week') && !markup.includes('[object Object]'))
        const restored = JSON.parse(JSON.stringify({ ...chat.initialRoutine, generated: result.routine }))
        const myRoutine = renderToStaticMarkup(createElement(RoutineView, { routine: restored }))
        assert.match(myRoutine, /class="routine-maker"/)
        assert.ok(myRoutine.includes(routine.summary))
      } finally {
        fetch.mock.restore()
      }
    }
  }
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

test('saved JSON recommendations restore while older Markdown recommendations remain readable', async () => {
  await translations.setLanguage('en')
  const routine = {
    name: 'Saved plan', summary: 'A short explanation.', recovery: 'Rest between days.',
    days: [{
      day: 1, day_type: 'Push', info: 'Warm up.', duration_minutes: 45,
      exercises: [{ exercise_id: 1, name: 'Catalog Press', sets: 3, reps: '8-12', rest_seconds: 90, notes: '' }],
    }],
  }
  const storageKey = 'form-routine-v1:77'
  try {
    for (const generated of [routine, '## Previous recommendation\n\nUse controlled reps.']) {
      const stored = { ...chat.initialRoutine, generated }
      storage.set(storageKey, JSON.stringify(stored))
      const markup = renderToStaticMarkup(createElement(ThemeContext.Provider, {
        value: { theme: 'light', resolvedTheme: 'light', setTheme: () => {} },
      }, createElement(MainView, { user: { id: 77, username: 'Test User' }, onSwitchUser: () => {} })))
      assert.ok(!markup.includes('Could not restore your routine'))
      assert.deepEqual(JSON.parse(storage.get(storageKey)), stored)
      const view = renderToStaticMarkup(createElement(RoutineView, { routine: stored }))
      assert.ok(view.includes(typeof generated === 'string' ? 'Previous recommendation' : 'A short explanation.'))
      assert.ok(!view.includes('[object Object]'))
    }
  } finally {
    storage.delete(storageKey)
  }
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
    const message = language === 'en' ? 'Selected as your current routine.' : 'Seleccionada como tu rutina actual.'
    const fetch = mock.method(globalThis, 'fetch', async () => Response.json({
      subsystem: 'routine_maker',
      response: { status: 'saved', message, routine, routine_id: 42, draft_id: null },
    }))
    try {
      const signal = new AbortController().signal
      const buttonSave = await chat.requestRoutineSave('session', 'draft', signal, language.toUpperCase(), 7)
      const chatSave = await chat.requestChat('Save this routine', 'session', signal, language.toUpperCase(), 7)
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

test('saved routine responses require a valid routine and database ID for either save path', async () => {
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
      await assert.rejects(chat.requestRoutineSave('session', 'draft', signal, 'EN', 7), /invalid response/)
    } finally {
      fetch.mock.restore()
    }
  }
})

test('direct save surfaces stale drafts and server failures without falling back to chat', async () => {
  for (const status of [422, 500]) {
    const fetch = mock.method(globalThis, 'fetch', async () => Response.json({
      detail: [{ msg: 'This draft is no longer available.' }],
    }, { status }))
    try {
      await assert.rejects(
        chat.requestRoutineSave('session', 'old-draft', new AbortController().signal, 'EN', 7),
        new RegExp(`HTTP ${status}`),
      )
      assert.equal(fetch.mock.callCount(), 1)
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
    assert.deepEqual(JSON.parse(calls[4].options.body), { query: 'Hi', language: 'EN', user_id: 7 })
    assert.ok(calls.every(({ options }) => options.method === 'POST'))
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
