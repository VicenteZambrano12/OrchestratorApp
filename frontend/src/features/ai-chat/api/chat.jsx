/**
 * @file Agent-chat API boundary and illustrative offline reply fixtures.
 * Live requests POST to the orchestrator, consume NDJSON progress (or JSON
 * responses), validate subsystem-specific results, and normalize renderable data.
 * Confirmed routine drafts are saved through the user routine endpoint; failed
 * saves retain draft context for recovery rather than masquerading as success.
 *
 * @typedef {object} ChatResult
 * @property {string} subsystem - Validated specialist identifier.
 * @property {string|import('../../ExplainerCard/exercise-data/exerciseData').Exercise[]} content - Markdown or exercise cards.
 * @property {import('../../PastRoutinesReport/report-data/reportData').PastRoutinesAnalysis} [analysis] - Structured history report.
 * @property {import('../../RoutineMaker/routine-data/routineData').RoutinePlan|string|null} [routine] - Structured live plan or demo Markdown.
 * @property {{id?: number, name: string}|null} [savedRoutine] - Persistence feedback.
 * @property {boolean} [awaitingConfirmation] - Whether to show explicit draft confirmation.
 * @property {boolean} [saveRequested] - Whether the chat action requires a client-side save.
 * @property {number} [routineId] - Saved routine identity if supplied.
 * @property {string|null} [draftId] - Backend draft identity for confirmation.
 * @property {object[]} [steps] - Accumulated execution-stage metadata.
 */
import i18n from 'i18next'
import { isExerciseList } from '../../ExplainerCard/exercise-data/exerciseData'
import { isPastRoutinesAnalysis } from '../../PastRoutinesReport/report-data/reportData'
import { demoPastRoutinesAnalysis } from '../../PastRoutinesReport/report-data/demoAnalysis'
import { isRoutinePlan } from '../../RoutineMaker/routine-data/routineData'
import { saveUserRoutine } from '../../../hooks/session/users'
import { readChatStream } from './readChatStream'
import { observedFetch, observeOperation } from '../../../lib/observability/http'

export const subsystemNames = {
  routine_maker: 'Routine maker',
  exercise_explainer: 'Exercise explainer',
  past_routines_analyzer: 'Progress analyzer',
  no_system: 'General guidance',
}

/**
 * Creates local illustrative targets, not a persisted catalog-backed exercise.
 * @param {string} name - Exercise name.
 * @param {string} muscle - Muscle label.
 * @param {number} sets - Planned set count.
 * @param {string} reps - Rep target.
 * @param {number} weight - Example load.
 * @param {string} [rest='90 sec'] - Unit-suffixed rest.
 * @returns {import('../../RoutineMaker/routine-data/routineData').WorkoutExercise} Demo exercise.
 */
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

export const initialMessages = []

/**
 * Produces explicitly illustrative replies after an abortable simulated delay.
 * @param {string} query - Demo prompt used for simple example routing.
 * @param {AbortSignal} signal - Cancellation for the simulated request.
 * @returns {Promise<ChatResult>} Example content without contacting the backend.
 */
export async function demoReply(query, signal) {
  // 1. Simulate latency while allowing the owning view to cancel pending feedback.
  await new Promise((resolve, reject) => {
    /** @returns {void} Cancels the simulated reply and rejects with native abort semantics. */
    const onAbort = () => { clearTimeout(timer); reject(new DOMException('Request cancelled', 'AbortError')) }
    const timer = setTimeout(() => { signal.removeEventListener('abort', onAbort); resolve() }, 1100)
    signal.addEventListener('abort', onAbort, { once: true })
  })
  // 2. Select an illustrative specialist response; none of these fixtures are live output.
  if (/explain|deadlift|technique|how to do/i.test(query)) {
    return { subsystem: 'exercise_explainer', content: '### Movement spotlight: Romanian deadlift\n\nThis is an **example explanation** for the demo. Live API can answer your specific exercise question.\n\n1. Stand tall with a soft bend in your knees and the weight close to your legs.\n2. Push your hips back, keeping your spine neutral.\n3. Lower only as far as you can maintain control, then drive your hips forward to stand.\n\n**Coach’s cue:** Think “hips back,” not “bend down.” Start light, and stop if you feel pain.' }
  }
  if (/progress|analy|review|last (push|pull|leg)|compar|week|history/i.test(query)) {
    const analysis = demoPastRoutinesAnalysis(query)
    return { subsystem: 'past_routines_analyzer', content: analysis.llm_explain, analysis }
  }
  if (/routine|plan|muscle|strength|schedule/i.test(query)) {
    return { subsystem: 'routine_maker', content: 'Here’s an **illustrative starting plan**, not a personalized assessment. The demo uses the same 3-day split; live mode can tailor it to your requirements.\n\n' + demoRoutine + '\n\nSave this recommendation to your routine, then adjust the exercise targets to suit your level.', routine: demoRoutine }
  }
  return { subsystem: 'no_system', content: 'Small, repeatable steps beat a perfect plan you can’t sustain.\n\nTry choosing **three consistent training days**, preparing your gym kit the night before, and tracking one small win after every session.\n\nThis is example coaching in demo mode. Switch to **Live API** for a response to your specific question.' }
}

/**
 * Runs one agent turn and follows a confirmed client-save request when present.
 * @param {string} query - User prompt.
 * @param {string} sessionId - Backend conversation key.
 * @param {AbortSignal} signal - View-owned cancellation.
 * @param {'EN'|'ES'} language - Request/response language.
 * @param {number} [userId] - Persisted profile; enables client-managed routine saving.
 * @param {(steps: object[]) => void} [onProgress] - Receives copied, ID-deduplicated stages.
 * @param {(data: object, endpoint: string) => void} [onResponse] - Workflow inspector response sink.
 * @returns {Promise<ChatResult>} Normalized reply with accumulated progress.
 * @throws {Error} Propagates request failures; save failures carry routineToSave draft context.
 */
export async function requestChat(query, sessionId, signal, language, userId, onProgress, onResponse) {
  // 1. Keep ordered progress stable when an existing stage is updated by ID.
  const steps = []
  /**
   * Publishes a stage snapshot only while the request is active.
   * @param {object} step - Validated progress event.
   * @returns {void}
   */
  const report = (step) => {
    if (signal?.aborted) return
    const index = steps.findIndex(({ id }) => id === step.id)
    if (index === -1) steps.push(step)
    else steps[index] = step
    onProgress?.([...steps])
  }
  // 2. Request the orchestrator turn and attach observed stages to its result.
  const result = await requestChatAction(
    `${encodeURIComponent(sessionId)}/chat`,
    { query, language, ...(userId === undefined ? {} : { user_id: userId, client_saves_routine: true }) },
    signal, language, userId, report, onResponse,
  )
  result.steps = [...steps]
  if (!result.saveRequested) return result
  // 3. Persist explicit save requests; retain the draft on failure for a UI retry.
  try {
    signal?.throwIfAborted()
    report({ id: 'routine_save', label: 'Saving your confirmed routine' })
    const saved = await requestRoutineSave(sessionId, result.routine, result.draftId, signal, language, userId, onResponse)
    return { ...saved, steps: [...steps] }
  } catch (error) {
    error.routineToSave = result
    throw error
  }
}

/**
 * Confirms a specific agent draft through versioned user-routine persistence.
 * @param {string} sessionId - Conversation owning the draft.
 * @param {import('../../RoutineMaker/routine-data/routineData').RoutinePlan} routine - Confirmed plan.
 * @param {string} draftId - Nonempty backend draft ID.
 * @param {AbortSignal} signal - View-owned cancellation.
 * @param {'EN'|'ES'} language - Supported confirmation language.
 * @param {number} userId - Positive persisted profile ID.
 * @param {(data: object, endpoint: string) => void} [onResponse] - Inspector response sink.
 * @returns {Promise<ChatResult>} Localized saved-routine reply.
 * @throws {Error} For invalid confirmation context or failed persistence.
 */
export async function requestRoutineSave(sessionId, routine, draftId, signal, language, userId, onResponse) {
  // 1. Require complete profile, conversation, and draft identity before confirming.
  if (!['EN', 'ES'].includes(language)) throw new Error('Chat language must be EN or ES.')
  if (!Number.isSafeInteger(userId) || userId < 1) throw new Error('Routine user ID must be a positive integer.')
  if (typeof sessionId !== 'string' || !sessionId.trim()) throw new Error(i18n.t('The chat API returned an invalid response.'))
  if (typeof draftId !== 'string' || !draftId.trim()) throw new Error(i18n.t('The chat API returned an invalid response.'))
  // 2. Persist the draft before emitting save feedback or clearing confirmation state.
  const saved = await saveUserRoutine(userId, routine, signal, { sessionId, draftId, language })
  onResponse?.(saved, 'PUT /users/{user_id}/routine')
  const t = i18n.getFixedT(language.toLowerCase())
  return {
    subsystem: 'routine_maker',
    content: t('Saved as a new version and selected as your current routine.'),
    routine: saved,
    savedRoutine: { name: saved.name },
    awaitingConfirmation: false,
    draftId: null,
  }
}

/**
 * Handles one live chat HTTP exchange and subsystem-specific response validation.
 * @param {string} path - Encoded conversation action path relative to the API base.
 * @param {object} payload - Query, language, and optional profile/save context.
 * @param {AbortSignal} signal - Caller cancellation.
 * @param {'EN'|'ES'} language - Translation language captured for this request.
 * @param {number} [userId] - Optional persisted profile ID.
 * @param {(step: object) => void} onProgress - Validated execution-stage callback.
 * @param {(data: object, endpoint: string) => void} [onResponse] - Raw response inspector.
 * @returns {Promise<ChatResult>} Validated render model.
 * @throws {Error} For invalid inputs/payloads, HTTP errors, stream failure, or timeout.
 * Network/5xx errors carry backendDown so the view can select its unavailable UI.
 */
async function requestChatAction(path, payload, signal, language, userId, onProgress, onResponse) {
  // 1. Validate request context and capture a 90-second deadline for the whole turn.
  if (!['EN', 'ES'].includes(language)) throw new Error('Chat language must be EN or ES.')
  if (userId !== undefined && (!Number.isSafeInteger(userId) || userId < 1)) throw new Error('Routine user ID must be a positive integer.')
  const t = i18n.getFixedT(language.toLowerCase())
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const timeoutSignal = AbortSignal.timeout(90000)
  try {
    let response
    try {
      // 2. Request NDJSON progress over fetch; do not create SSE/WebSocket connections.
      response = await observedFetch('/{id}/chat', `${baseUrl}/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
        body: JSON.stringify(payload),
        signal: AbortSignal.any([signal, timeoutSignal]),
      })
    } catch (error) {
      if (error instanceof TypeError) {
        const unreachable = new Error(t('The backend could not be reached.'), { cause: error })
        unreachable.backendDown = true
        throw unreachable
      }
      throw error
    }
    // 3. Preserve validation details and classify server failures for fallback routing.
    if (!response.ok) {
      if (response.status === 422 && response.headers.get('content-type')?.includes('application/json')) {
        const body = await response.json()
        if (Array.isArray(body.detail) && body.detail.every((item) => typeof item.msg === 'string')) {
          throw new Error(`${t('The chat API returned HTTP {{status}}. Check that the backend is running and your request is valid.', { status: response.status })} ${body.detail.map((item) => item.msg).join(' ')}`)
        }
      }
      const error = new Error(t('The chat API returned HTTP {{status}}. Check that the backend is running and your request is valid.', { status: response.status }))
      error.backendDown = response.status >= 500
      throw error
    }
    // 4. Consume streaming progress or the compatible JSON response through completion.
    const data = await observeOperation('chat.read_response', () =>
      response.headers?.get('content-type')?.includes('application/x-ndjson')
        ? readChatStream(response, onProgress, t)
        : response.json(), AbortSignal.any([signal, timeoutSignal]))
    // 5. Validate the selected specialist's contract before exposing renderable content.
    if (!data || typeof data !== 'object') throw new Error(t('The chat API returned an invalid response.'))
    if (!Object.hasOwn(subsystemNames, data.subsystem)) throw new Error(t('The chat API returned an unknown subsystem.'))
    onResponse?.(data, 'POST /{id}/chat')
    if (typeof data.response === 'string') return { subsystem: data.subsystem, content: data.response }
    if (data.subsystem === 'exercise_explainer') {
      if (!isExerciseList(data.response)) throw new Error(t('The chat API returned an invalid exercise list.'))
      return { subsystem: data.subsystem, content: data.response }
    }
    if (data.subsystem === 'past_routines_analyzer') {
      if (!isPastRoutinesAnalysis(data.response)) throw new Error(t('The chat API returned an invalid response.'))
      return { subsystem: data.subsystem, content: data.response.llm_explain, analysis: data.response }
    }
    // 6. Keep routine draft/confirmation state explicit rather than inferring a save.
    const result = data.response
    if (!result || typeof result.message !== 'string' ||
      !['awaiting_confirmation', 'save_requested', 'saved', 'needs_parameters', 'needs_changes', 'needs_routine', 'no_match'].includes(result.status)) {
      throw new Error(t('The chat API returned an invalid response.'))
    }
    const routine = result.routine
    if (routine !== null && !isRoutinePlan(routine)) {
      throw new Error(t('The chat API returned an invalid response.'))
    }
    if (['awaiting_confirmation', 'save_requested'].includes(result.status) &&
      (!routine || typeof result.draft_id !== 'string' || !result.draft_id.trim())) {
      throw new Error(t('The chat API returned an invalid response.'))
    }
    if (result.status === 'saved' &&
      (!routine || !Number.isSafeInteger(result.routine_id) || result.routine_id < 1)) {
      throw new Error(t('The chat API returned an invalid response.'))
    }
    return {
      subsystem: data.subsystem,
      content: result.message,
      routine,
      savedRoutine: result.status === 'saved' ? { id: result.routine_id, name: result.routine.name } : null,
      awaitingConfirmation: result.status === 'awaiting_confirmation',
      saveRequested: result.status === 'save_requested',
      routineId: result.routine_id,
      draftId: result.draft_id,
    }
  } catch (error) {
    // 7. Translate deadline expiry while preserving all other failures for the caller.
    if (timeoutSignal.aborted) throw new Error(t('The coach took too long to respond. Please try again.'), { cause: error })
    throw error
  }
}
