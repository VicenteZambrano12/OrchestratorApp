import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../../i18n'
import {
  Activity, ArrowRight, ArrowUp,
  ChevronRight, CircleHelp, Dumbbell, Flame,
  AlertCircle, MessageSquare, Plus, RotateCcw, Sparkles, X,
} from 'lucide-react'
import BrandMark from '../../components/BrandMark/BrandMark'
import Pipeline from '../../components/Pipeline/Pipeline'
import TrainingPanel from '../../components/TrainingPanel/TrainingPanel'
import ThemeToggle from '../../components/ThemeToggle/ThemeToggle'
import LanguageToggle from '../../components/LanguageToggle/LanguageToggle'
import FailingView from '../FailingView/FailingView'
import RoutineView from '../../components/RoutineView/RoutineView'
import { SubsystemResponse } from '../../features/ai-chat/components/SubsystemResponse'
import { initialMessages, initialRoutine, requestChat, requestRoutineSave } from '../../features/ai-chat/api/chat'
import UserDialog from '../../components/UserDialog/UserDialog'
import { setSessionKey } from '../../hooks/session/users'
import { isRoutinePlan } from '../../features/RoutineMaker/routine-data/routineData'

function loadRoutine(routineStorageKey) {
  try {
    const saved = localStorage.getItem(routineStorageKey)
    if (!saved) return { routine: initialRoutine, error: '' }
    const routine = JSON.parse(saved)
    if (!Array.isArray(routine.days) || routine.days.length !== 3 ||
      !routine.days.every((day) => typeof day.name === 'string' && Array.isArray(day.exercises) &&
        day.exercises.every((exercise) => typeof exercise.name === 'string' &&
          Number.isInteger(exercise.sets) && exercise.sets >= 1 && exercise.sets <= 10 &&
          typeof exercise.reps === 'string' && exercise.reps.trim() &&
          Number.isFinite(exercise.weight) && exercise.weight >= 0 &&
          typeof exercise.completed === 'boolean')) ||
      (typeof routine.generated !== 'string' && !isRoutinePlan(routine.generated))) {
      throw new Error('The saved routine is not valid.')
    }
    return { routine, error: '' }
  } catch (error) {
    return { routine: initialRoutine, error: i18n.t('Could not restore your routine: {{message}}', { message: i18n.t(error.message) }) }
  }
}

function HelpDialog({ onClose }) {
  const { t } = useTranslation()
  const dialogRef = useRef(null)
  useEffect(() => {
    const dialog = dialogRef.current
    dialog.showModal()
    return () => dialog.close()
  }, [])

  return <dialog ref={dialogRef} className="help-dialog" aria-labelledby="help-title"
    onCancel={(event) => { event.preventDefault(); onClose() }}
    onClick={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="help-modal">
      <button className="icon-button modal-close" aria-label={t('Close guidance')} autoFocus onClick={onClose}><X size={20} /></button>
      <BrandMark /><h2 id="help-title">{t('Meet your new training partner.')}</h2>
      <p>{t('Use AI Chat for workout ideas, exercise explanations, and progress reviews. Expand the pipeline to see which specialist handled a request.')}</p>
      <p>{t('Requests use your selected language. Include any relevant history or routine in your message.')}</p>
      <p>{t('My Routine is an editable demo workout. Your sets, weights, completion, and saved coach recommendation stay on this device.')}</p>
      <p>{t('Exercise explanations include interactive cards with images, instructions, and coach insights. Other responses use Markdown.')}</p>
      <button className="primary-button" onClick={onClose}>{t('Got it')} <ArrowRight size={16} /></button>
    </section>
  </dialog>
}

function MainView({ user, onSwitchUser }) {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage.toUpperCase()
  const routineStorageKey = `form-routine-v1:${user.id}`
  const initials = user.username.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase()
  const [restored] = useState(() => loadRoutine(routineStorageKey))
  const [tab, setTab] = useState('chat')
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [savingRoutine, setSavingRoutine] = useState(false)
  const [backendDown, setBackendDown] = useState(false)
  const [routine, setRoutine] = useState(restored.routine)
  const [error, setError] = useState(restored.error)
  const [saved, setSaved] = useState(false)
  const [help, setHelp] = useState(false)
  const [userDialog, setUserDialog] = useState(false)
  const sessionId = String(user.id)
  const [lastQuery, setLastQuery] = useState('')
  const conversationRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    if (messages.length > initialMessages.length || pending) {
      const conversation = conversationRef.current
      conversation?.scrollTo({ top: conversation.scrollHeight, behavior: 'smooth' })
    }
  }, [messages, pending])

  function saveRoutine(next) {
    try {
      localStorage.setItem(routineStorageKey, JSON.stringify(next))
      setSaved(true)
      setError('')
    } catch (storageError) {
      setSaved(false)
      setError(t('Could not save on this device: {{message}}', { message: storageError.message }))
    }
  }

  function askCoach(prompt) {
    setInput(prompt)
    setTab('chat')
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  function receiveResponse(result) {
    if (result.savedRoutine) {
      const next = { ...routine, generated: result.routine }
      setRoutine(next)
      saveRoutine(next)
      setLastQuery('')
    }
    setMessages((current) => [
      ...current.map((message) => result.savedRoutine ? { ...message, awaitingConfirmation: false } : message),
      { id: crypto.randomUUID(), role: 'assistant', ...result, demo: false },
    ])
  }

  function sendMessage(event) {
    event.preventDefault()
    if (!input.trim() || pending) return
    submitQuery(input.trim())
  }

  function retryLast() {
    if (lastQuery && !pending) submitQuery(lastQuery, true)
  }

  async function submitQuery(query, isRetry = false) {
    setLastQuery(query)
    if (!isRetry) setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', content: query }])
    setInput('')
    setPending(true)
    setError('')
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const result = await requestChat(query, sessionId, controller.signal, language, user.id)
      if (controller.signal.aborted) return
      receiveResponse(result)
    } catch (requestError) {
      if (controller.signal.aborted) return
      if (requestError.backendDown) setBackendDown(true)
      else if (requestError.name !== 'AbortError') setError(`${t(requestError.message)} ${t('Your message was not answered. You can retry it below.')}`)
      if (!isRetry) setInput(query)
    } finally {
      setPending(false)
    }
  }

  async function newChat() {
    if (pending) return
    setPending(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await setSessionKey(sessionId, controller.signal, true)
      if (controller.signal.aborted) return
      setMessages([])
      setInput('')
      setError('')
      setLastQuery('')
    } catch (error) {
      if (!controller.signal.aborted) setError(t('Could not initialize user session: {{message}}', { message: error.message }))
    } finally {
      if (!controller.signal.aborted) setPending(false)
    }
  }

  async function confirmRoutine(message) {
    if (pending) return
    setPending(true)
    setSavingRoutine(true)
    setLastQuery('')
    setError('')
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const result = await requestRoutineSave(sessionId, message.draftId, controller.signal, language, user.id)
      if (controller.signal.aborted) return
      receiveResponse(result)
    } catch (requestError) {
      if (!controller.signal.aborted) setError(t('Could not save routine: {{message}}', { message: requestError.message }))
    } finally {
      setSavingRoutine(false)
      if (!controller.signal.aborted) setPending(false)
    }
  }

  if (backendDown) return <FailingView onRetry={() => setBackendDown(false)} />

  return <div className={`app-shell${tab === 'chat' ? ' chat-shell' : ''}`}>
    <aside className="sidebar">
      <a className="brand" href="#chat" onClick={() => setTab('chat')}><BrandMark /><span>form<span className="brand-period">.</span></span></a>
      <div className="workspace-label">{t('YOUR PERSONAL COACH')}</div>
      <nav aria-label={t('Main navigation')}><button className={tab === 'chat' ? 'nav-item active' : 'nav-item'} aria-current={tab === 'chat' ? 'page' : undefined} onClick={() => setTab('chat')}><MessageSquare size={19} />{t('AI Chat')}<span className="nav-active-dot" /></button><button className={tab === 'routine' ? 'nav-item active' : 'nav-item'} aria-current={tab === 'routine' ? 'page' : undefined} onClick={() => setTab('routine')}><Dumbbell size={19} />{t('My Routine')}<span className="nav-active-dot" /></button></nav>
      <button className="new-chat" onClick={() => { newChat(); setTab('chat') }} disabled={pending}><Plus size={17} />{t('New conversation')}</button>
      <div className="sidebar-note"><span className="note-symbol"><Activity size={22} /></span><h4>{t('Better together.')}</h4><p>{t('Your goals. Our intelligence.')}<br />{t('A stronger you.')}</p><div className="note-line"><span /><span /><span /></div></div>
      <div className="sidebar-bottom"><button className="help-button" onClick={() => setHelp(true)}><CircleHelp size={18} />{t('A little guidance')}<ArrowRight size={15} /></button><button type="button" className="profile user-profile" aria-label={t('Change user: {{name}}', { name: user.username })} aria-haspopup="dialog" onClick={() => setUserDialog(true)}><span className="avatar">{initials}</span><div><strong>{user.username}</strong><span>{t('Your fitness journey')}</span></div><span className="profile-status" /></button></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumbs">{t('Your workspace')}<ChevronRight size={14} /><strong>{t(tab === 'chat' ? 'AI Chat' : 'My Routine')}</strong></div><div className="topbar-right"><span className="private-label"><span className="status-dot" />{t('Your space to grow')}</span><LanguageToggle /><ThemeToggle /><button type="button" className="header-avatar user-avatar" aria-label={t('Change user: {{name}}', { name: user.username })} aria-haspopup="dialog" onClick={() => setUserDialog(true)}>{initials}</button></div></header>
      {tab === 'chat' ? <div className="chat-layout">
        <main className="chat-main">
          <div className="chat-scroll-area" ref={conversationRef} tabIndex={0} role="region" aria-label={t('AI Chat')}>
          <div className="chat-intro"><div className="intro-kicker"><Sparkles size={15} /> {t('A LITTLE GUIDANCE. A LOT OF POTENTIAL.')}</div><h1>{t('Your goals. A smarter plan')}<span>.</span></h1><p>{t('Meet your AI coach. Built to understand you, designed to move you forward.')}</p></div>
          <div className="conversation-header"><span><span className="status-dot" />{t(messages.length ? 'Let’s build your next chapter' : 'A fresh start')}</span><button className="icon-button" aria-label={t('Start a new conversation')} title={t('Start a new conversation')} onClick={newChat} disabled={pending}><RotateCcw size={15} /></button></div>
          <div className="conversation" aria-live="polite" aria-busy={pending}>
            {messages.length === 0 && <div className="empty-chat"><BrandMark /><h2>{t('Good things start with a conversation.')}</h2><p>{t("Tell me what you're working toward, or pick a prompt below.")}</p><button type="button" className="primary-button" onClick={() => askCoach(t('Create a 3-day push/pull/legs routine for an intermediate lifter, with 1 hour per session.'))}><Dumbbell size={16} aria-hidden="true" />{t('Build my routine')}</button></div>}
            {messages.map((message) => <article className={`message ${message.role}`} key={message.id}>
              <div className="message-avatar">{message.role === 'assistant' ? <BrandMark small /> : <span className="avatar">{initials}</span>}</div>
              <div className="message-body"><div className="message-heading"><strong>{t(message.role === 'assistant' ? 'Form coach' : 'You')}</strong><span>{message.role === 'assistant' ? <><span className="ai-label">{t('AI')}</span>{message.demo && t('Example response')}</> : t('Just now')}</span></div>
                {message.role === 'assistant' && !message.savedRoutine && <Pipeline subsystem={message.subsystem} demo={message.demo} />}
                <SubsystemResponse subsystem={message.subsystem} content={message.content} savedRoutine={message.savedRoutine} routine={message.routine} onExplainExercise={(name) => askCoach(t('Explain how to do {{exercise}}.', { exercise: name }))} />
                {message.awaitingConfirmation && <button className="primary-button" disabled={pending || message !== messages.at(-1)} onClick={() => confirmRoutine(message)}>{t('Save routine to database')}</button>}
              </div>
            </article>)}
            {pending && <article className="message assistant"><div className="message-avatar"><BrandMark small /></div><div className="message-body"><div className="message-heading"><strong>{t('Form coach')}</strong><span>{t('Working on it…')}</span></div>{savingRoutine ? <p>{t('Saving routine…')}</p> : <Pipeline pending demo={false} />}</div></article>}
          </div>
          {error && <div className="error-message" role="alert"><AlertCircle size={16} aria-hidden="true" /><span>{error}</span>{lastQuery && <button type="button" className="retry-button" disabled={pending} onClick={() => retryLast()}><RotateCcw size={14} aria-hidden="true" />{t('Retry')}</button>}</div>}
          </div>
          <div className="composer-area"><div className="suggestions"><button onClick={() => askCoach(t('Create a 3-day push/pull/legs routine for an intermediate lifter, with 1 hour per session.'))} disabled={pending}><Dumbbell size={14} />{t('Build my routine')}</button><button onClick={() => askCoach(t('Explain how to do a Romanian deadlift.'))} disabled={pending}><Activity size={14} />{t('Explain an exercise')}</button><button onClick={() => askCoach(t('Analyze my progress. What workout details should I share?'))} disabled={pending}><Flame size={14} />{t('Review my progress')}</button></div>
            <form className="composer" onSubmit={sendMessage}><textarea ref={inputRef} aria-label={t('Message your AI coach')} placeholder={t('A goal, a question, a fresh start. What’s on your mind?')} value={input} onChange={(event) => setInput(event.target.value)} disabled={pending} rows={2} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form.requestSubmit() } }} /><div className="composer-bottom"><span><Sparkles size={14} />{t('Your goals, expertly orchestrated')}</span><div><span className="enter-hint">{t('Enter to send')}</span><button type="submit" className="send-button" aria-label={t('Send message')} disabled={!input.trim() || pending}><ArrowUp size={20} /></button></div></div></form>
            <p className="composer-disclaimer">{t('AI is a guide, not a substitute for professional advice. Listen to your body.')}</p>
          </div>
        </main>
        <TrainingPanel routine={routine} onOpen={() => setTab('routine')} onPrompt={askCoach} />
      </div> : <main className="routine-main"><RoutineView routine={routine} setRoutine={setRoutine} onAsk={askCoach} onSave={saveRoutine} saved={saved} error={error} /></main>}
      <footer className="app-footer"><span>{t('Made for the long run.')}</span><span>{t('FORM / YOUR PERSONAL AI COACH')}</span></footer>
    </div>
    {help && <HelpDialog onClose={() => setHelp(false)} />}
    {userDialog && <UserDialog user={user} onSwitch={onSwitchUser} onClose={() => setUserDialog(false)} />}
  </div>
}

export default MainView
