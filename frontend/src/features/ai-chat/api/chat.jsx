export const subsystemNames = {
  routine_maker: 'Routine maker',
  exercise_explainer: 'Exercise explainer',
  past_routines_analyzer: 'Progress analyzer',
  no_system: 'General guidance',
}

const exercise = (name, muscle, sets, reps, weight, rest = '90 sec') => ({ name, muscle, sets, reps, weight, rest, completed: false })

export const initialRoutine = {
  generated: '',
  days: [
    { name: 'Push', focus: 'Chest, shoulders & triceps', exercises: [
      exercise('Barbell bench press', 'Chest', 3, '8–10', 40, '2 min'),
      exercise('Incline dumbbell press', 'Upper chest', 3, '10–12', 16),
      exercise('Seated shoulder press', 'Shoulders', 3, '8–10', 12),
      exercise('Dumbbell lateral raise', 'Side delts', 3, '12–15', 6, '60 sec'),
      exercise('Cable triceps pushdown', 'Triceps', 3, '12–15', 15, '60 sec'),
    ] },
    { name: 'Pull', focus: 'Back & biceps', exercises: [
      exercise('Lat pulldown', 'Back', 3, '10–12', 35),
      exercise('Seated cable row', 'Mid back', 3, '10–12', 30),
      exercise('Single-arm dumbbell row', 'Lats', 3, '10–12', 16),
      exercise('Face pull', 'Rear delts', 3, '12–15', 10, '60 sec'),
      exercise('Dumbbell curl', 'Biceps', 3, '10–12', 8, '60 sec'),
    ] },
    { name: 'Legs', focus: 'Quads, hamstrings & glutes', exercises: [
      exercise('Barbell squat', 'Quads & glutes', 3, '8–10', 40, '2 min'),
      exercise('Romanian deadlift', 'Hamstrings', 3, '8–10', 35, '2 min'),
      exercise('Leg press', 'Quads', 3, '10–12', 80),
      exercise('Seated leg curl', 'Hamstrings', 3, '12–15', 25),
      exercise('Standing calf raise', 'Calves', 3, '15–20', 20, '60 sec'),
    ] },
  ],
}

const demoRoutine = '### Your 3-day training week\n\n- **Monday · Push** — Chest, shoulders, and triceps\n- **Wednesday · Pull** — Back and biceps\n- **Friday · Legs** — Quads, hamstrings, and glutes\n\nStart with **3 sets per exercise**, leaving 1–2 reps in reserve. Use a weight you can control, and rest for 60–120 seconds between sets.'

export const initialMessages = [
  { id: 'welcome-user', role: 'user', content: 'I want to get stronger and build muscle. I can train 3 days a week, about an hour each session. Where should I start?' },
  { id: 'welcome-coach', role: 'assistant', subsystem: 'routine_maker', demo: true, content: 'Love that. A clear goal and a realistic schedule are a great place to start. 🌱\n\nA **3-day Push / Pull / Legs split** gives each muscle group focused attention, with plenty of room to recover between sessions.\n\n' + demoRoutine + '\n\nI’ve put together a starting plan for you below. We can fine-tune it to your experience, equipment, and what feels good for your body.', routine: demoRoutine },
]

export async function demoReply(query, signal) {
  await new Promise((resolve, reject) => {
    const onAbort = () => { clearTimeout(timer); reject(new DOMException('Request cancelled', 'AbortError')) }
    const timer = setTimeout(() => { signal.removeEventListener('abort', onAbort); resolve() }, 1100)
    signal.addEventListener('abort', onAbort, { once: true })
  })
  if (/explain|deadlift|technique|how to do/i.test(query)) {
    return { subsystem: 'exercise_explainer', content: '### Movement spotlight: Romanian deadlift\n\nThis is an **example explanation** for the demo. Live API can answer your specific exercise question.\n\n1. Stand tall with a soft bend in your knees and the weight close to your legs.\n2. Push your hips back, keeping your spine neutral.\n3. Lower only as far as you can maintain control, then drive your hips forward to stand.\n\n**Coach’s cue:** Think “hips back,” not “bend down.” Start light, and stop if you feel pain.' }
  }
  if (/progress|analy|review/i.test(query)) {
    return { subsystem: 'past_routines_analyzer', content: '### Let’s look at the bigger picture\n\nTo review your progress, share your **last 2–4 weeks of workouts**, including:\n\n- Exercises, sets, reps, and weights\n- How difficult the last set felt\n- Sleep, recovery, and any discomfort\n\nThis demo hasn’t analyzed your history. In live mode, paste those details into your message so the progress specialist has the context it needs.' }
  }
  if (/routine|plan|muscle|strength|schedule/i.test(query)) {
    return { subsystem: 'routine_maker', content: 'Here’s an **illustrative starting plan**, not a personalized assessment. The demo uses the same 3-day split; live mode can tailor it to your requirements.\n\n' + demoRoutine + '\n\nSave this recommendation to your routine, then adjust the exercise targets to suit your level.', routine: demoRoutine }
  }
  return { subsystem: 'no_system', content: 'Small, repeatable steps beat a perfect plan you can’t sustain. 🌱\n\nTry choosing **three consistent training days**, preparing your gym kit the night before, and tracking one small win after every session.\n\nThis is example coaching in demo mode. Switch to **Live API** for a response to your specific question.' }
}

export async function requestChat(query, sessionId, signal) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const timeoutSignal = AbortSignal.timeout(90000)
  try {
    let response
    try {
      response = await fetch(`${baseUrl}/${encodeURIComponent(sessionId)}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, language: 'EN' }),
        signal: AbortSignal.any([signal, timeoutSignal]),
      })
    } catch (error) {
      if (error instanceof TypeError) {
        const unreachable = new Error('The backend could not be reached.', { cause: error })
        unreachable.backendDown = true
        throw unreachable
      }
      throw error
    }
    if (!response.ok) {
      const error = new Error(`The chat API returned HTTP ${response.status}. Check that the backend is running and your request is valid.`)
      error.backendDown = response.status >= 500
      throw error
    }
    const data = await response.json()
    if (!Object.hasOwn(subsystemNames, data.subsystem)) throw new Error('The chat API returned an unknown subsystem.')
    if (typeof data.response === 'string') return { subsystem: data.subsystem, content: data.response }
    const result = data.response
    if (!result || typeof result.message !== 'string' ||
      !['created', 'updated', 'needs_parameters', 'no_match'].includes(result.status) ||
      (result.routine !== null && typeof result.routine !== 'string')) {
      throw new Error('The chat API returned an invalid response.')
    }
    return { subsystem: data.subsystem, content: [result.message, result.routine].filter(Boolean).join('\n\n'), routine: ['created', 'updated'].includes(result.status) ? result.routine : null }
  } catch (error) {
    if (timeoutSignal.aborted) throw new Error('The coach took too long to respond. Please try again.', { cause: error })
    throw error
  }
}
