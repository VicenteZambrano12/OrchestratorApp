/**
 * @file User-scoped application workspace coordinating chat, routines, and workouts.
 * Owns agent request lifecycles, NDJSON progress snapshots, response inspection, and
 * recoverable failure UI. API utilities validate/normalize orchestrator responses;
 * child views render structured specialists without taking ownership of transport.
 *
 * App keys this view by user ID so a profile change clears conversation, routine,
 * and workout state. Separate cancellation refs isolate chat, routine reads,
 * version updates, and performed-workout writes.
 */
import { useEffect, useRef, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import {
  Activity, ArrowRight, ArrowUp,
  ChevronRight, CircleHelp, Dumbbell, Flame,
  AlertCircle, MessageSquare, Plus, RotateCcw, Sparkles, X,
} from 'lucide-react'
import BrandMark from '../../components/BrandMark/BrandMark'
import Pipeline from '../../components/Pipeline/Pipeline'
import WorkflowMonitor from '../../components/WorkflowMonitor/WorkflowMonitor'
import TrainingPanel from '../../components/TrainingPanel/TrainingPanel'
import ThemeToggle from '../../components/ThemeToggle/ThemeToggle'
import LanguageToggle from '../../components/LanguageToggle/LanguageToggle'
import FailingView from '../FailingView/FailingView'
import RoutineView from '../../components/RoutineView/RoutineView'
import { SubsystemResponse } from '../../features/ai-chat/components/SubsystemResponse'
import { initialMessages, requestChat, requestRoutineSave } from '../../features/ai-chat/api/chat'
import UserDialog from '../../components/UserDialog/UserDialog'
import { getUserRoutine, saveUserRoutine, setSessionKey } from '../../hooks/session/users'
import { toRoutinePlan, toWorkoutRoutine } from '../../features/RoutineMaker/routine-data/routineData'
import { useWorkoutSession } from '../../features/RoutineView/workout-session/useWorkoutSession'
import { saveWorkout } from '../../features/RoutineView/workout-session/workoutApi'
import AdaptiveDialog from '../../components/AdaptiveDialog/AdaptiveDialog'

/**
 * Explains the workspace's specialist routing and saved-routine behavior.
 * @param {object} props - Guidance dialog properties.
 * @param {() => void} props.onClose - Parent-owned dismissal.
 * @returns {import('react').ReactElement} Localized native guidance modal.
 */
function HelpDialog({ onClose }) {
  const { t } = useTranslation()
  return <AdaptiveDialog className="help-dialog" aria-labelledby="help-title" onClose={onClose}>
    <section className="help-modal">
      <button className="icon-button modal-close" aria-label={t('Close guidance')} autoFocus onClick={onClose}><X size={20} /></button>
      <BrandMark /><h2 id="help-title">{t('Meet your new training partner.')}</h2>
      <p>{t('Use AI Chat for workout ideas, exercise explanations, and progress reviews. Follow each request through its live coaching steps.')}</p>
      <p>{t('Requests use your selected language. Include any relevant history or routine in your message.')}</p>
      <p>{t('My Routine shows the active routine saved to your profile.')}</p>
      <p>{t('Exercise explanations include interactive cards with images, instructions, and coach insights. Other responses use Markdown.')}</p>
      <button className="primary-button" onClick={onClose}>{t('Got it')} <ArrowRight size={16} /></button>
    </section>
  </AdaptiveDialog>
}

/**
 * Renders chat/routine navigation and coordinates all user-specific backend work.
 * Translation context supplies both UI copy and the EN/ES request language.
 * Local state separates pending work, observed execution trace, saved routine
 * identity, editable workout state, and error recovery; the session hook owns
 * active workout timing/sets independently of the selected navigation tab.
 * @param {object} props - Workspace properties.
 * @param {import('../../hooks/session/users').UserProfile} props.user - Initialized active profile.
 * @param {(user: import('../../hooks/session/users').UserProfile, signal?: AbortSignal) => Promise<void>} props.onSwitchUser - Activates another backend session.
 * @returns {import('react').ReactElement} User workspace, recovery view, and optional dialogs.
 */
function MainView({ user, onSwitchUser }) {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage.toUpperCase()
  const initials = user.username.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase()
  const [tab, setTab] = useState('chat')
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  // One mutation gate prevents overlapping chat/reset/confirmation operations.
  const [pending, setPending] = useState(false)
  const [pendingSteps, setPendingSteps] = useState([])
  // Keep actual execution/response data separate from the monitor's visual playback.
  const [trace, setTrace] = useState({ query: '', steps: [], status: 'idle', error: '' })
  const [savingRoutine, setSavingRoutine] = useState(false)
  // Transport/5xx failures replace the shell; validation/timeouts remain inline.
  const [backendDown, setBackendDown] = useState(false)
  const [error, setError] = useState('')
  const [activeRoutine, setActiveRoutine] = useState(null)
  // Persisted identity is required to attach actual sets to the correct routine version.
  const [activeRoutineId, setActiveRoutineId] = useState(null)
  const workoutSession = useWorkoutSession()
  // Async chat callbacks must observe the latest workout lock, not a stale closure.
  const workoutActiveRef = useRef(false)
  const [workout, setWorkout] = useState(null)
  const [workoutSaved, setWorkoutSaved] = useState(false)
  const [workoutUpdated, setWorkoutUpdated] = useState(false)
  const [routineLoading, setRoutineLoading] = useState(false)
  const [routineError, setRoutineError] = useState('')
  const [help, setHelp] = useState(false)
  const [userDialog, setUserDialog] = useState(false)
  const sessionId = String(user.id)
  const [lastQuery, setLastQuery] = useState('')
  const conversationRef = useRef(null)
  const latestAssistantRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)
  const routineAbortRef = useRef(null)
  const updateAbortRef = useRef(null)
  const workoutAbortRef = useRef(null)

  useEffect(() => {
    // 1. Mirror the current workout lock for callbacks awaiting agent responses.
    workoutActiveRef.current = workoutSession.isWorkoutActive
  }, [workoutSession.isWorkoutActive])

  useEffect(() => () => {
    // 1. Cancel each independent request domain when this user-scoped view unmounts.
    abortRef.current?.abort()
    routineAbortRef.current?.abort()
    updateAbortRef.current?.abort()
    workoutAbortRef.current?.abort()
  }, [])

  /**
   * Refreshes the saved routine without overwriting an active workout.
   * @returns {void} Starts an abortable read and publishes loading/error state.
   */
  function loadActiveRoutine() {
    // 1. Preserve the active workout; replace only a previous routine-read request.
    if (workoutSession.isWorkoutActive) return
    routineAbortRef.current?.abort()
    const controller = new AbortController()
    routineAbortRef.current = controller
    // 2. Expose loading and require routine metadata for future workout persistence.
    setRoutineLoading(true)
    setRoutineError('')
    getUserRoutine(user.id, controller.signal, { includeMetadata: true })
      .then(({ routine: loadedRoutine, routineId }) => {
        if (controller.signal.aborted) return
        // 3. Keep unsaved session edits unless the backend's version/content changed.
        if (routineId !== activeRoutineId || JSON.stringify(loadedRoutine) !== JSON.stringify(activeRoutine)) {
          setWorkout(loadedRoutine ? toWorkoutRoutine(loadedRoutine) : null)
          setWorkoutSaved(false)
          setWorkoutUpdated(false)
        }
        setActiveRoutine(loadedRoutine)
        setActiveRoutineId(routineId)
      })
      .catch((requestError) => {
        // 4. Discard unavailable data and show retry instead of an apparent empty plan.
        if (!controller.signal.aborted) {
          setActiveRoutine(null)
          setActiveRoutineId(null)
          setWorkout(null)
          setWorkoutSaved(false)
          setWorkoutUpdated(false)
          setRoutineError(requestError.message)
        }
      })
      .finally(() => {
        // 5. Only the surviving read may clear the current loading state.
        if (!controller.signal.aborted) setRoutineLoading(false)
      })
  }

  /** @returns {void} Selects routine navigation and requests current persisted data. */
  function openRoutine() {
    // 1. Navigate immediately while the routine view renders its loading boundary.
    setTab('routine')
    loadActiveRoutine()
  }
  useEffect(() => {
    // 1. Avoid scrolling the untouched welcome state.
    if (messages.length > initialMessages.length || pending) {
      const conversation = conversationRef.current
      const latestAssistant = latestAssistantRef.current
      // 2. Align completed replies at their start; follow the bottom during progress.
      if (!pending && messages.at(-1)?.role === 'assistant' && conversation && latestAssistant) {
        const top = conversation.scrollTop + latestAssistant.getBoundingClientRect().top - conversation.getBoundingClientRect().top
        conversation.scrollTo({ top, behavior: 'smooth' })
      } else {
        conversation?.scrollTo({ top: conversation.scrollHeight, behavior: 'smooth' })
      }
    }
  }, [messages, pending, pendingSteps])

  /**
   * Seeds a user-reviewable prompt instead of sending a request automatically.
   * @param {string} prompt - Suggested or exercise-specific message.
   * @returns {void}
   */
  function askCoach(prompt) {
    // 1. Activate the composer with the suggested prompt.
    setInput(prompt)
    setTab('chat')
    // 2. Wait for chat navigation to mount the input before moving focus.
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  /**
   * Appends a normalized reply and synchronizes a saved plan when workout-safe.
   * @param {import('../../features/ai-chat/api/chat').ChatResult} result - Validated API reply.
   * @returns {void}
   */
  function receiveResponse(result) {
    // 1. Do not replace a routine whose indices still belong to an active workout.
    if (result.savedRoutine && !workoutActiveRef.current) {
      setLastQuery('')
      routineAbortRef.current?.abort()
      setRoutineLoading(false)
      setRoutineError('')
      setActiveRoutine(result.routine)
      setActiveRoutineId(null)
      setWorkout(toWorkoutRoutine(result.routine))
      setWorkoutSaved(false)
      setWorkoutUpdated(false)
    }
    // 2. Retire older confirmations after a save and append a distinct assistant turn.
    setMessages((current) => [
      ...current.map((message) => result.savedRoutine ? { ...message, awaitingConfirmation: false } : message),
      { id: crypto.randomUUID(), role: 'assistant', ...result, demo: false },
    ])
  }

  /**
   * Records response snapshots for the live monitor, not the observability logger.
   * @param {object} data - API response exposed to the user-facing inspector.
   * @param {string} endpoint - Templated endpoint label.
   * @returns {void}
   */
  function receiveApiResponse(data, endpoint) {
    setTrace((current) => ({
      ...current, response: data,
      responses: [...(current.responses ?? []), { endpoint, data }],
    }))
  }

  /**
   * Submits a trimmed composer message only when no mutation is pending.
   * @param {import('react').SubmitEvent<HTMLFormElement>} event - Composer submission.
   * @returns {void}
   */
  function sendMessage(event) {
    // 1. Keep submission client-side and reject empty/overlapping requests.
    event.preventDefault()
    if (!input.trim() || pending) return
    // 2. Delegate request state and streaming to the shared turn handler.
    submitQuery(input.trim())
  }

  /** @returns {void} Replays the last failed prompt without duplicating its user bubble. */
  function retryLast() {
    if (lastQuery && !pending) submitQuery(lastQuery, true)
  }

  /**
   * Runs one orchestrator turn and reconciles progress, drafts, and recoverable errors.
   * @param {string} query - Nonempty trimmed user prompt.
   * @param {boolean} [isRetry=false] - Reuses the existing user message.
   * @returns {Promise<void>} Settles after completion, cancellation, or visible failure.
   */
  async function submitQuery(query, isRetry = false) {
    // 1. Lock the composer and reset per-turn trace/error state before backend work.
    setLastQuery(query)
    if (!isRetry) setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', content: query }])
    setInput('')
    setPending(true)
    setPendingSteps([])
    setTrace({ id: crypto.randomUUID(), query, steps: [], status: 'running', error: '' })
    setError('')
    // 2. Bind this turn to view cleanup and stream validated execution stages to state.
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const result = await requestChat(query, sessionId, controller.signal, language, user.id, (steps) => {
        setPendingSteps(steps)
        setTrace((current) => ({ ...current, steps }))
      }, receiveApiResponse)
      // 3. Publish a completed reply only if this user-scoped request is still active.
      if (controller.signal.aborted) return
      setTrace((current) => ({ ...current, status: 'complete' }))
      receiveResponse(result)
    } catch (requestError) {
      // 4. Preserve unsaved drafts; distinguish backend outage from inline turn errors.
      if (controller.signal.aborted) return
      setTrace((current) => ({ ...current, status: 'failed', error: requestError.message }))
      if (requestError.routineToSave) {
        receiveResponse({ ...requestError.routineToSave, content: '', awaitingConfirmation: true, saveRequested: false })
        setLastQuery('')
        setError(t('Could not save routine: {{message}}', { message: requestError.message }))
        return
      }
      if (requestError.backendDown) setBackendDown(true)
      else if (requestError.name !== 'AbortError') setError(`${t(requestError.message)} ${t('Your message was not answered. You can retry it below.')}`)
      if (!isRetry) setInput(query)
    } finally {
      // 5. Release the mutation gate so failures can be corrected or retried.
      setPending(false)
    }
  }

  /**
   * Resets backend conversation state before clearing the visible transcript.
   * @returns {Promise<void>} Failed resets preserve the current conversation and show an error.
   */
  async function newChat() {
    // 1. Serialize reset with chat/save work and retain the current transcript.
    if (pending) return
    setPending(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      // 2. Clear local history only after the backend acknowledges a fresh session.
      await setSessionKey(sessionId, controller.signal, true)
      if (controller.signal.aborted) return
      setMessages([])
      setPendingSteps([])
      setTrace({ query: '', steps: [], status: 'idle', error: '' })
      setInput('')
      setError('')
      setLastQuery('')
    } catch (error) {
      // 3. Keep history on failure and unlock only a still-mounted request.
      if (!controller.signal.aborted) setError(t('Could not initialize user session: {{message}}', { message: error.message }))
    } finally {
      if (!controller.signal.aborted) setPending(false)
    }
  }

  /**
   * Persists the selected agent draft and updates chat/save feedback.
   * @param {import('../../features/ai-chat/api/chat').ChatResult} message - Latest confirmable draft.
   * @returns {Promise<void>} Save errors remain visible without discarding the draft.
   */
  async function confirmRoutine(message) {
    // 1. Lock conversation mutations and start a dedicated save trace.
    if (pending) return
    setPending(true)
    setSavingRoutine(true)
    const saveSteps = [{ id: 'routine_maker', label: 'Routine maker' }, { id: 'routine_save', label: 'Saving your confirmed routine' }]
    setTrace({ id: crypto.randomUUID(), query: t('Save routine to database'), steps: saveSteps, status: 'running', error: '' })
    setLastQuery('')
    setError('')
    const controller = new AbortController()
    abortRef.current = controller
    try {
      // 2. Confirm the exact draft, not a newly inferred plan from message text.
      const result = await requestRoutineSave(sessionId, message.routine, message.draftId, controller.signal, language, user.id, receiveApiResponse)
      if (controller.signal.aborted) return
      setTrace((current) => ({ ...current, status: 'complete' }))
      receiveResponse(result)
    } catch (requestError) {
      // 3. Keep the confirmation actionable and mark the observed save as failed.
      if (!controller.signal.aborted) setTrace((current) => ({ ...current, status: 'failed', error: requestError.message }))
      if (!controller.signal.aborted) setError(t('Could not save routine: {{message}}', { message: requestError.message }))
    } finally {
      // 4. Restore controls after save completion without updating an aborted view.
      setSavingRoutine(false)
      if (!controller.signal.aborted) setPending(false)
    }
  }

  /**
   * Converts edited targets and saves a new active routine version.
   * @param {import('../../features/RoutineMaker/routine-data/routineData').WorkoutRoutine} editedRoutine - Controlled editor draft.
   * @returns {Promise<void>} Rejects to the confirmation dialog on conversion/save failure.
   */
  async function updateWorkout(editedRoutine) {
    // 1. Serialize only valid catalog-backed targets, excluding actual weights/completion.
    const plan = toRoutinePlan(editedRoutine)
    const controller = new AbortController()
    updateAbortRef.current = controller
    // 2. Require the saved version ID before allowing subsequent workout history writes.
    const { routine: saved, routineId } = await saveUserRoutine(user.id, plan, controller.signal, { includeMetadata: true })
    controller.signal.throwIfAborted()
    // 3. Cancel stale reads before publishing the acknowledged version and feedback.
    routineAbortRef.current?.abort()
    setRoutineLoading(false)
    setRoutineError('')
    setActiveRoutine(saved)
    setActiveRoutineId(routineId)
    setWorkoutSaved(true)
    setWorkoutUpdated(true)
  }

  /**
   * Records performed sets against the current saved routine/day identity.
   * @param {Array<{exercise_id: number, reps: number, weight: number|null}>} sets - Normalized actual sets.
   * @returns {ReturnType<import('../../features/RoutineView/workout-session/workoutApi').saveWorkout>} Save receipt.
   */
  async function finishWorkout(sets) {
    // 1. Preserve per-day legacy identity when available; otherwise use active version ID.
    const controller = new AbortController()
    workoutAbortRef.current = controller
    const routineId = workout.days[workoutSession.dayIndex].routineId ?? activeRoutineId
    // 2. Resolve only after persistence so the child can safely release its workout lock.
    const result = await saveWorkout(user.id, routineId, sets, controller.signal)
    controller.signal.throwIfAborted()
    return result
  }

  // Hide rather than unmount the shell during outages, preserving drafts for recovery.
  return <>{backendDown && <FailingView onRetry={() => setBackendDown(false)} />}
    <div className={`app-shell${tab === 'chat' ? ' chat-shell' : ''}`} style={backendDown ? { display: 'none' } : undefined}>
    <a className="skip-link" href="#workspace-content">{t('Skip to main content')}</a>
    <aside className="sidebar">
      <a className="brand" href="#chat" onClick={() => setTab('chat')}><BrandMark /><span>form<span className="brand-period">.</span></span></a>
      <div className="workspace-label">{t('YOUR PERSONAL COACH')}</div>
      <nav aria-label={t('Main navigation')}><button className={tab === 'chat' ? 'nav-item active' : 'nav-item'} aria-current={tab === 'chat' ? 'page' : undefined} onClick={() => setTab('chat')}><MessageSquare size={19} />{t('AI Chat')}<span className="nav-active-dot" /></button><button className={tab === 'routine' ? 'nav-item active' : 'nav-item'} aria-current={tab === 'routine' ? 'page' : undefined} onClick={openRoutine}><Dumbbell size={19} />{t('My Routine')}<span className="nav-active-dot" /></button></nav>
      <button className="new-chat" onClick={() => { newChat(); setTab('chat') }} disabled={pending}><Plus size={17} />{t('New conversation')}</button>
      <div className="sidebar-note"><span className="note-symbol"><Activity size={22} /></span><h4>{t('Better together.')}</h4><p>{t('Your goals. Our intelligence.')}<br />{t('A stronger you.')}</p><div className="note-line"><span /><span /><span /></div></div>
      <div className="sidebar-bottom"><button className="help-button" onClick={() => setHelp(true)}><CircleHelp size={18} />{t('A little guidance')}<ArrowRight size={15} /></button><button type="button" className="profile user-profile" aria-label={t('Change user: {{name}}', { name: user.username })} aria-haspopup="dialog" onClick={() => setUserDialog(true)}><span className="avatar">{initials}</span><div><strong>{user.username}</strong><span>{t('Your fitness journey')}</span></div><span className="profile-status" /></button></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumbs">{t('Your workspace')}<ChevronRight size={14} /><strong>{t(tab === 'chat' ? 'AI Chat' : 'My Routine')}</strong></div><div className="topbar-right"><WorkflowMonitor trace={trace} /><span className="private-label"><span className="status-dot" />{t('Your space to grow')}</span><LanguageToggle /><ThemeToggle /><button type="button" className="icon-button" aria-label={t('A little guidance')} aria-haspopup="dialog" onClick={() => setHelp(true)}><CircleHelp size={20} aria-hidden="true" /></button><button type="button" className="header-avatar user-avatar" aria-label={t('Change user: {{name}}', { name: user.username })} aria-haspopup="dialog" onClick={() => setUserDialog(true)}>{initials}</button></div></header>
      {tab === 'chat' ? <div className="chat-layout">
        <main className="chat-main" id="workspace-content" tabIndex={-1}>
          <div className="chat-scroll-area" ref={conversationRef} tabIndex={0} role="region" aria-label={t('AI Chat')}>
          <div className="chat-intro"><div className="intro-kicker"><Sparkles size={15} /> {t('A LITTLE GUIDANCE. A LOT OF POTENTIAL.')}</div><h1>{t('Your goals. A smarter plan')}<span>.</span></h1><p>{t('Meet your AI coach. Built to understand you, designed to move you forward.')}</p></div>
          <div className="conversation-header"><span><span className="status-dot" />{t(messages.length ? 'Let’s build your next chapter' : 'A fresh start')}</span><button className="icon-button" aria-label={t('Start a new conversation')} title={t('Start a new conversation')} onClick={newChat} disabled={pending}><RotateCcw size={15} /></button></div>
          <div className="conversation" aria-live="polite" aria-busy={pending}>
            {messages.length === 0 && <div className="empty-chat"><BrandMark /><h2>{t('Good things start with a conversation.')}</h2><p>{t("Tell me what you're working toward, or pick a prompt below.")}</p><button type="button" className="primary-button" onClick={() => askCoach(t('Create a 3-day gym routine to build muscle for an intermediate lifter, with 1 hour per session.'))}><Dumbbell size={16} aria-hidden="true" />{t('Build my routine')}</button></div>}
            {messages.map((message) => <article className={`message ${message.role}`} key={message.id} ref={message.role === 'assistant' && message === messages.at(-1) ? latestAssistantRef : undefined}>
              <div className="message-avatar">{message.role === 'assistant' ? <BrandMark small /> : <span className="avatar">{initials}</span>}</div>
              <div className="message-body"><div className="message-heading"><strong>{t(message.role === 'assistant' ? 'Form coach' : 'You')}</strong><span>{message.role === 'assistant' ? <><span className="ai-label">{t('AI')}</span>{message.demo && t('Example response')}</> : t('Just now')}</span></div>
                {message.role === 'assistant' && <Pipeline steps={message.steps} />}
                <SubsystemResponse subsystem={message.subsystem} content={message.content} savedRoutine={message.savedRoutine} routine={message.routine} analysis={message.analysis} onExplainExercise={(name) => askCoach(t('Explain how to do {{exercise}}.', { exercise: name }))} />
                {message.awaitingConfirmation && <button className="primary-button" disabled={pending || message !== messages.at(-1)} onClick={() => confirmRoutine(message)}>{t('Save routine to database')}</button>}
              </div>
            </article>)}
            {pending && <article className="message assistant"><div className="message-avatar"><BrandMark small /></div><div className="message-body"><div className="message-heading"><strong>{t('Form coach')}</strong><span>{t('Working on it…')}</span></div>{savingRoutine ? <p>{t('Saving routine…')}</p> : <Pipeline pending steps={pendingSteps} />}</div></article>}
          </div>
          {!pending && error && <Pipeline steps={pendingSteps} failed />}
          {error && <div className="error-message" role="alert"><AlertCircle size={16} aria-hidden="true" /><span>{error}</span>{lastQuery && <button type="button" className="retry-button" disabled={pending} onClick={() => retryLast()}><RotateCcw size={14} aria-hidden="true" />{t('Retry')}</button>}</div>}
          </div>
          <div className="composer-area"><div className="suggestions"><button onClick={() => askCoach(t('Create a 3-day gym routine to build muscle for an intermediate lifter, with 1 hour per session.'))} disabled={pending}><Dumbbell size={14} />{t('Build my routine')}</button><button onClick={() => askCoach(t('Explain how to do a barbell deadlift, which muscles it works, and common mistakes to avoid.'))} disabled={pending}><Activity size={14} />{t('Explain an exercise')}</button><button onClick={() => askCoach(t('Analyze my saved workouts from the last 7 days and summarize my consistency, training volume, and progress.'))} disabled={pending}><Flame size={14} />{t('Review my progress')}</button></div>
            <form className="composer" onSubmit={sendMessage}><textarea ref={inputRef} aria-label={t('Message your AI coach')} placeholder={t('A goal, a question, a fresh start. What’s on your mind?')} value={input} onChange={(event) => setInput(event.target.value)} disabled={pending} rows={2} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form.requestSubmit() } }} /><div className="composer-bottom"><span><Sparkles size={14} />{t('Your goals, expertly orchestrated')}</span><div><span className="enter-hint">{t('Enter to send')}</span><button type="submit" className="send-button" aria-label={t('Send message')} disabled={!input.trim() || pending}><ArrowUp size={20} /></button></div></div></form>
            <p className="composer-disclaimer">{t('AI is a guide, not a substitute for professional advice. Listen to your body.')}</p>
          </div>
        </main>
        <TrainingPanel key={user.id} userId={user.id} routineRevision={activeRoutine} onOpen={openRoutine} onPrompt={askCoach} />
      </div> : <main className="routine-main" id="workspace-content" tabIndex={-1}>
        {routineLoading ? <p role="status">{t('Loading your routine…')}</p> :
          routineError ? <div role="alert" className="error-message"><AlertCircle size={16} aria-hidden="true" /><span>{t('Could not load routine: {{message}}', { message: routineError })}</span><button type="button" className="retry-button" onClick={loadActiveRoutine}>{t('Retry')}</button></div> :
            workout ? <RoutineView key={`${activeRoutineId}:${JSON.stringify(activeRoutine)}`} routine={workout} setRoutine={setWorkout} onAsk={askCoach} onSave={() => { setWorkoutSaved(true); setWorkoutUpdated(false) }} onUpdate={updateWorkout} onFinishWorkout={activeRoutineId ? finishWorkout : undefined} workoutSession={workoutSession} weightUnit={user.weight_unit ?? 'kg'} saved={workoutSaved} savedMessage={workoutUpdated ? 'Routine updated and selected as your active routine.' : 'Changes saved for this session.'} /> :
              <section className="empty-routine"><h1>{t('No saved routine yet')}</h1><p>{t('Save a routine from AI Chat to see your current training plan here.')}</p><button className="primary-button" onClick={() => askCoach(t('Create a 3-day push/pull/legs routine for an intermediate lifter, with 1 hour per session.'))}>{t('Build my routine')} <ArrowRight size={16} /></button></section>}
      </main>}
      <footer className="app-footer"><span>{t('Made for the long run.')}</span><span>{t('FORM / YOUR PERSONAL AI COACH')}</span></footer>
    </div>
    <AnimatePresence>
      {help && <HelpDialog key="help" onClose={() => setHelp(false)} />}
      {userDialog && <UserDialog key="user" user={user} onSwitch={onSwitchUser} onClose={() => setUserDialog(false)} />}
    </AnimatePresence>
  </div></>
}

export default MainView
