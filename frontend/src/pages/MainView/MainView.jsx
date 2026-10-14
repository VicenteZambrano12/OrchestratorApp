import { useEffect, useRef, useState } from 'react'
import {
  Activity, ArrowRight, ArrowUp, CheckCheck,
  ChevronRight, CircleHelp, Dumbbell, Flame,
  MessageSquare, Plus, RotateCcw, Sparkles, X,
} from 'lucide-react'
import BrandMark from '../../components/BrandMark/BrandMark'
import Pipeline from '../../components/Pipeline/Pipeline'
import RoutinePreview from '../../components/RoutinePreview/RoutinePreview'
import TrainingPanel from '../../components/TrainingPanel/TrainingPanel'
import FailingView from '../FailingView/FailingView'
import RoutineView from '../../components/RoutineView/RoutineView'
import { SubsystemResponse } from '../../features/ai-chat/components/SubsystemResponse'
import { initialMessages, initialRoutine, requestChat } from '../../features/ai-chat/api/chat'
import '../../App.css'

const routineStorageKey = 'form-routine-v1'

function loadRoutine() {
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
      typeof routine.generated !== 'string') {
      throw new Error('The saved routine is not valid.')
    }
    return { routine, error: '' }
  } catch (error) {
    return { routine: initialRoutine, error: `Could not restore your routine: ${error.message}` }
  }
}

function HelpDialog({ onClose }) {
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
      <button className="icon-button modal-close" aria-label="Close guidance" autoFocus onClick={onClose}><X size={20} /></button>
      <BrandMark /><h2 id="help-title">Meet your new training partner.</h2>
      <p>Use AI Chat for workout ideas, exercise explanations, and progress reviews. Expand the pipeline to see which specialist handled a request.</p>
      <p>Requests are sent in English to the backend. The endpoint is stateless: include any relevant history or routine in your message.</p>
      <p>My Routine is an editable demo workout. Your sets, weights, completion, and saved coach recommendation stay on this device. Specialist responses currently use Markdown; custom subsystem templates can be added later.</p>
      <button className="primary-button" onClick={onClose}>Got it <ArrowRight size={16} /></button>
    </section>
  </dialog>
}

function MainView() {
  const [restored] = useState(loadRoutine)
  const [tab, setTab] = useState('chat')
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [backendDown, setBackendDown] = useState(false)
  const [routine, setRoutine] = useState(restored.routine)
  const [error, setError] = useState(restored.error)
  const [saved, setSaved] = useState(false)
  const [help, setHelp] = useState(false)
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    if (messages.length > initialMessages.length || pending) bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, pending])

  function saveRoutine(next) {
    try {
      localStorage.setItem(routineStorageKey, JSON.stringify(next))
      setSaved(true)
      setError('')
    } catch (storageError) {
      setSaved(false)
      setError(`Could not save on this device: ${storageError.message}`)
    }
  }

  function askCoach(prompt) {
    setInput(prompt)
    setTab('chat')
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  function saveRecommendation(content) {
    const next = { ...routine, generated: content }
    setRoutine(next)
    saveRoutine(next)
    setTab('routine')
  }

  async function sendMessage(event) {
    event.preventDefault()
    if (!input.trim() || pending) return
    const query = input.trim()
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', content: query }])
    setInput('')
    setPending(true)
    setError('')
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const result = await requestChat(query, sessionId, controller.signal)
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', ...result, demo: false }])
    } catch (requestError) {
      if (requestError.backendDown) setBackendDown(true)
      else if (requestError.name !== 'AbortError') setError(`${requestError.message} Your message was not answered. You can retry it below.`)
      setInput(query)
    } finally {
      setPending(false)
    }
  }

  function newChat() {
    if (pending) return
    setMessages([])
    setSessionId(crypto.randomUUID())
    setInput('')
    setError('')
  }

  if (backendDown) return <FailingView onRetry={() => setBackendDown(false)} />

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#chat" onClick={() => setTab('chat')}><BrandMark /><span>form<span className="brand-period">.</span></span></a>
      <div className="workspace-label">YOUR PERSONAL COACH</div>
      <nav aria-label="Main navigation"><button className={tab === 'chat' ? 'nav-item active' : 'nav-item'} onClick={() => setTab('chat')}><MessageSquare size={19} />AI Chat<span className="nav-active-dot" /></button><button className={tab === 'routine' ? 'nav-item active' : 'nav-item'} onClick={() => setTab('routine')}><Dumbbell size={19} />My Routine<span className="nav-active-dot" /></button></nav>
      <button className="new-chat" onClick={() => { newChat(); setTab('chat') }} disabled={pending}><Plus size={17} />New conversation</button>
      <div className="sidebar-note"><span className="note-symbol"><Activity size={22} /></span><h4>Better together.</h4><p>Your goals. Our intelligence.<br />A stronger you.</p><div className="note-line"><span /><span /><span /></div></div>
      <div className="sidebar-bottom"><button className="help-button" onClick={() => setHelp(true)}><CircleHelp size={18} />A little guidance<ArrowRight size={15} /></button><div className="profile"><span className="avatar">JD</span><div><strong>Jamie Davis</strong><span>Your fitness journey</span></div><span className="profile-status" /></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumbs">Your workspace<ChevronRight size={14} /><strong>{tab === 'chat' ? 'AI Chat' : 'My Routine'}</strong></div><div className="topbar-right"><span className="private-label"><span className="status-dot" />Your space to grow</span><span className="header-avatar">JD</span></div></header>
      {tab === 'chat' ? <div className="chat-layout">
        <main className="chat-main">
          <div className="chat-intro"><div className="intro-kicker"><Sparkles size={15} /> A LITTLE GUIDANCE. A LOT OF POTENTIAL.</div><h1>Your goals. A smarter plan<span>.</span></h1><p>Meet your AI coach. Built to understand you, designed to move you forward.</p></div>
          <div className="conversation-header"><span><span className="status-dot" />{messages.length ? 'Let’s build your next chapter' : 'A fresh start'}</span><button className="icon-button" aria-label="Start a new conversation" title="Start a new conversation" onClick={newChat} disabled={pending}><RotateCcw size={15} /></button></div>
          <div className="conversation" aria-live="polite" aria-busy={pending}>
            {messages.length === 0 && <div className="empty-chat"><BrandMark /><h2>Good things start with a conversation.</h2><p>Tell me what you&apos;re working toward, or pick a prompt below.</p></div>}
            {messages.map((message) => <article className={`message ${message.role}`} key={message.id}>
              <div className="message-avatar">{message.role === 'assistant' ? <BrandMark small /> : <span className="avatar">JD</span>}</div>
              <div className="message-body"><div className="message-heading"><strong>{message.role === 'assistant' ? 'Form coach' : 'You'}</strong><span>{message.role === 'assistant' ? <><span className="ai-label">AI</span>{message.demo && 'Example response'}</> : 'Just now'}</span></div>
                {message.role === 'assistant' && <Pipeline subsystem={message.subsystem} demo={message.demo} />}
                <SubsystemResponse subsystem={message.subsystem} content={message.content} />
                {message.routine && <><RoutinePreview demo={message.demo} onOpen={() => saveRecommendation(message.routine)} /><div className="message-actions"><button onClick={() => saveRecommendation(message.routine)}><Plus size={14} />Save recommendation to My Routine</button><span><CheckCheck size={14} />Ready for your review</span></div></>}
              </div>
            </article>)}
            {pending && <article className="message assistant"><div className="message-avatar"><BrandMark small /></div><div className="message-body"><div className="message-heading"><strong>Form coach</strong><span>Working on it…</span></div><Pipeline pending demo={false} /></div></article>}
            <div ref={bottomRef} />
          </div>
          {error && <div className="error-message" role="alert">{error}</div>}
          <div className="composer-area"><div className="suggestions"><button onClick={() => askCoach('Create a 3-day push/pull/legs routine for an intermediate lifter, with 1 hour per session.')} disabled={pending}><Dumbbell size={14} />Build my routine</button><button onClick={() => askCoach('Explain how to do a Romanian deadlift.')} disabled={pending}><Activity size={14} />Explain an exercise</button><button onClick={() => askCoach('Analyze my progress. What workout details should I share?')} disabled={pending}><Flame size={14} />Review my progress</button></div>
            <form className="composer" onSubmit={sendMessage}><textarea ref={inputRef} aria-label="Message your AI coach" placeholder="A goal, a question, a fresh start. What’s on your mind?" value={input} onChange={(event) => setInput(event.target.value)} disabled={pending} rows={2} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form.requestSubmit() } }} /><div className="composer-bottom"><span><Sparkles size={14} />Your goals, expertly orchestrated</span><div><span className="enter-hint">Enter to send</span><button type="submit" className="send-button" aria-label="Send message" disabled={!input.trim() || pending}><ArrowUp size={20} /></button></div></div></form>
            <p className="composer-disclaimer">AI is a guide, not a substitute for professional advice. Listen to your body.</p>
          </div>
        </main>
        <TrainingPanel routine={routine} onOpen={() => setTab('routine')} onPrompt={askCoach} />
      </div> : <main className="routine-main"><RoutineView routine={routine} setRoutine={setRoutine} onAsk={askCoach} onSave={saveRoutine} saved={saved} error={error} /></main>}
      <footer className="app-footer"><span>Made for the long run.</span><span>FORM / YOUR PERSONAL AI COACH</span></footer>
    </div>
    {help && <HelpDialog onClose={() => setHelp(false)} />}
  </div>
}

export default MainView
