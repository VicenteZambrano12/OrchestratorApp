import { demoPastRoutinesAnalysis } from '../src/features/PastRoutinesReport/report-data/demoAnalysis.js'

export const user = { id: 7, username: 'Alex Morgan', weight_unit: 'kg' }
export const plan = {
  name: 'Balanced strength and mobility',
  summary: 'A flexible plan with controlled progress and time to recover.',
  recovery: 'Leave a recovery day between training sessions.',
  days: ['Push', 'Pull', 'Legs'].map((name, index) => ({
    day: index + 1, day_type: name, info: 'Use a comfortable range of motion.',
    duration_minutes: 45,
    exercises: [
      { exercise_id: 1, name: 'Bench Press', sets: 2, reps: '8-12', rest_seconds: 60, notes: 'Controlled tempo.' },
      { exercise_id: 2, name: 'Overhead Press', sets: 2, reps: '10', rest_seconds: 60, notes: '' },
    ],
  })),
}

const exercise = {
  id: 1, name: 'Barbell deadlift with controlled tempo',
  description: 'An exercise explanation with a long name and useful context.',
  instructions: ['Set your stance.', 'Move with control.'],
  media_urls: ['/test-frame-1.svg', '/test-frame-2.svg'],
  anatomy_diagram_url: '/test-anatomy.svg',
  llm_explanation: '### Coach guidance\n\nStart with a comfortable load and move with **control**.',
}

export async function mockWorkspace(page, { emptyRoutine = false, failWorkout = false } = {}) {
  const writes = []
  await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('**/test-*.svg', (route) => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 240"><rect width="400" height="240" fill="#18201d"/><path d="M100 120h200" stroke="#6ee7b7" stroke-width="12"/></svg>',
  }))
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/health') return route.fulfill({ json: { status: 'ok' } })
    if (path === '/api/users') return route.fulfill({ json: [user] })
    if (path === '/api/7/key') return route.fulfill({ json: {} })
    if (path === '/api/users/7/routine') {
      if (request.method() === 'PUT') {
        writes.push(request.postDataJSON())
        return route.fulfill({ headers: { 'X-Routine-Id': '42' }, json: request.postDataJSON() })
      }
      return route.fulfill({ headers: { 'X-Routine-Id': '42' }, json: emptyRoutine ? null : plan })
    }
    if (path === '/api/users/7/days') {
      return route.fulfill({ json: Array.from({ length: 7 }, (_, index) => ({
        date: `2026-10-${String(14 + index).padStart(2, '0')}`, has_routine: index % 2 === 0,
      })) })
    }
    if (path === '/api/7/chat') {
      const { query } = request.postDataJSON()
      if (/explain/i.test(query)) return route.fulfill({
        json: { subsystem: 'exercise_explainer', response: [exercise, { ...exercise, id: 2, name: 'Second exercise' }] },
      })
      if (/report|progress|compare|week|last workout/i.test(query)) return route.fulfill({
        json: { subsystem: 'past_routines_analyzer', response: demoPastRoutinesAnalysis(query) },
      })
      return route.fulfill({ json: {
        subsystem: 'routine_maker',
        response: { message: 'Your plan is ready for review.', status: 'awaiting_confirmation', routine: plan, draft_id: 'draft-1' },
      } })
    }
    if (request.method() === 'POST' && path.includes('workout')) {
      writes.push(request.postDataJSON())
      return route.fulfill({ status: failWorkout ? 503 : 200, json: { id: 1 } })
    }
    return route.fulfill({ status: 501, json: { detail: `Unmocked endpoint: ${path}` } })
  })
  return writes
}

export async function sendPrompt(page, query) {
  await page.getByRole('textbox', { name: 'Message your AI coach' }).fill(query)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
}
