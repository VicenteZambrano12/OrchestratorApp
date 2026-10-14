import { useEffect, useRef, useState } from 'react'
import {
  Activity, ArrowRight, ArrowUp, Check, CheckCheck, ChevronDown,
  ChevronRight, CircleHelp, Clock3, Dumbbell, Flame, Layers3,
  MessageSquare, Plus, RotateCcw, Sparkles, Target, X,
} from 'lucide-react'
import { SubsystemResponse } from './features/ai-chat/components/SubsystemResponse'
import { demoReply, initialMessages, initialRoutine, requestChat, subsystemNames } from './features/ai-chat/api/chat'
import './App.css'

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

function BrandMark({ small = false }) {
  return <span className={`brand-mark ${small ? 'small' : ''}`}><Layers3 size={small ? 17 : 22} strokeWidth={2.5} /></span>
}

function Pipeline({ subsystem, pending = false, demo = true }) {
  const [expanded, setExpanded] = useState(true)
  const stages = [
    { name: 'Orchestrator', detail: pending ? 'Routing your request' : 'Matched your request to the right specialist', icon: Layers3 },
    { name: subsystemNames[subsystem] || 'Specialist', detail: pending ? 'Waiting for the response' : 'Returned a response for your review', icon: Dumbbell },
    { name: 'Response', detail: pending ? 'Waiting for the response' : 'Ready to review', icon: CheckCheck },
  ]
  return (
    <div className={`pipeline ${pending ? 'is-pending' : ''}`}>
      <button className="pipeline-toggle" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
        <span><span className={pending ? 'status-dot pulsing' : 'status-dot'} />{pending ? 'Working on your request' : 'Your coaching team, in sync'}</span>
        <span className="pipeline-meta">{demo ? 'Demo pipeline' : 'Request status'}<ChevronDown size={14} className={expanded ? 'rotated' : ''} /></span>
      </button>
      {expanded && <div className="pipeline-stages">{stages.map(({ name, detail, icon: Icon }, index) => (
        <div className="pipeline-stage" key={name}>
          <span className="stage-icon"><Icon size={15} /></span>
          <div><strong>{name}</strong><p>{detail}</p></div>
          {!pending && <Check size={14} className="stage-check" />}
          {pending && index === 0 && <span className="loading-ring" />}
        </div>
      ))}<p className="pipeline-disclaimer">{demo ? 'Illustrative steps for this mockup.' : 'The API returns a final result, not live intermediate steps.'}</p></div>}
    </div>
  )
}

function RoutinePreview({ onOpen, demo }) {
  return <button className="routine-preview" onClick={onOpen}>
    <span className="preview-icon"><Dumbbell size={22} /></span>
    <span><strong>{demo ? 'Your next chapter starts here' : 'Your coach’s recommendation'}</strong><span>{demo ? '3-day Push / Pull / Legs · Example plan' : 'Markdown plan · Ready to review'}</span></span>
    <span className="preview-action">View plan <ArrowRight size={16} /></span>
  </button>
}

function TrainingPanel({ routine, onOpen, onPrompt }) {
  const completed = routine.days.flatMap((day) => day.exercises).filter((exercise) => exercise.completed).length
  return <aside className="training-panel">
    <div className="panel-label">YOUR TRAINING <span className="tiny-pill">THIS WEEK</span></div>
    <div className="training-card">
      <div className="card-topline"><span className="eyebrow">BUILT AROUND YOU</span><Target size={18} /></div>
      <h3>A little stronger.<br />Every single week.</h3>
      <p>Consistency is the goal.<br />We&apos;ll take care of the plan.</p>
      <div className="barbell-art" aria-hidden="true">
        <svg viewBox="0 0 280 130" fill="none"><ellipse cx="140" cy="108" rx="98" ry="10" fill="#d6ded2" /><g transform="rotate(-17 140 65)"><rect x="27" y="61" width="226" height="12" rx="6" fill="#94a38b" /><rect x="50" y="30" width="23" height="74" rx="7" fill="#344c3b" /><rect x="73" y="39" width="15" height="56" rx="5" fill="#57745b" /><rect x="207" y="30" width="23" height="74" rx="7" fill="#344c3b" /><rect x="192" y="39" width="15" height="56" rx="5" fill="#57745b" /><path d="M57 38v58M214 38v58" stroke="#6f896f" strokeWidth="2" strokeLinecap="round" /></g><path d="m246 22 3 8 8 3-8 3-3 8-3-8-8-3 8-3Z" fill="#8eaa70" /><circle cx="37" cy="30" r="3" fill="#a9bc91" /></svg>
      </div>
      <div className="training-stats"><div><strong>3 <span>days</span></strong><small>Weekly frequency</small></div><div><strong>60 <span>min</span></strong><small>Session duration</small></div></div>
      <button className="panel-routine-button" onClick={onOpen}>Explore your routine <ArrowRight size={16} /></button>
    </div>
    <div className="week-card"><div><h4>Your weekly rhythm</h4><span>{completed} exercises logged</span></div><div className="week-days">{['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, index) => <div key={index}><span>{day}</span><span className={[0, 2, 4].includes(index) ? 'training-day' : ''}>{[0, 2, 4].includes(index) ? <Dumbbell size={14} /> : '–'}</span></div>)}</div><p><span className="status-dot" />Train. Recover. Repeat.</p></div>
    <div className="coach-tip"><span className="tip-icon"><Sparkles size={18} /></span><div><h4>Small steps. Real progress.</h4><p>A good plan adapts to your life, not the other way around.</p><button onClick={() => onPrompt('How can I stay consistent with my training?')}>Let&apos;s talk about your goals <ArrowRight size={13} /></button></div></div>
    <div className="powered"><BrandMark small /><span>One coach. A team of specialists.</span></div>
  </aside>
}

function RoutineView({ routine, setRoutine, onAsk, onSave, saved, error }) {
  const [dayIndex, setDayIndex] = useState(0)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(null)
  const [validation, setValidation] = useState('')
  const displayed = editing ? draft : routine
  const day = displayed.days[dayIndex]
  const complete = day.exercises.filter((exercise) => exercise.completed).length

  function changeExercise(index, field, value) {
    setDraft((current) => ({ ...current, days: current.days.map((item, i) => i === dayIndex
      ? { ...item, exercises: item.exercises.map((exercise, j) => j === index ? { ...exercise, [field]: value } : exercise) }
      : item) }))
  }

  function saveEdits() {
    if (draft.days.some((item) => item.exercises.some((exercise) => !Number.isInteger(Number(exercise.sets)) ||
      Number(exercise.sets) < 1 || Number(exercise.sets) > 10 || !exercise.reps.trim() ||
      exercise.weight === '' || !Number.isFinite(Number(exercise.weight)) || Number(exercise.weight) < 0))) {
      setValidation('Enter 1–10 sets, a rep target, and a weight of at least 0 kg.')
      return
    }
    const next = { ...draft, days: draft.days.map((item) => ({ ...item, exercises: item.exercises.map((exercise) => ({ ...exercise, sets: Number(exercise.sets), weight: Number(exercise.weight) })) })) }
    setRoutine(next)
    onSave(next)
    setEditing(false)
    setValidation('')
  }

  return <div className="routine-view">
    <div className="section-heading"><div><span className="eyebrow">YOUR PERSONAL PLAYBOOK</span><h1>A plan for your potential<span>.</span></h1><p>Show up for yourself. We&apos;ll handle the next step.</p></div><span className="plan-badge"><span className="status-dot" />Active plan</span></div>
    <div className="routine-summary"><div><Dumbbell size={20} /><span><small>Training split</small><strong>Push / Pull / Legs</strong></span></div><div><Clock3 size={20} /><span><small>Session length</small><strong>60 minutes</strong></span></div><div><Target size={20} /><span><small>Your focus</small><strong>Build strength</strong></span></div><span className="demo-label">Demo workout</span></div>
    {routine.generated && <section className="generated-routine"><div><Sparkles size={18} /><h3>Latest coach recommendation</h3></div><p>Review this recommendation alongside your editable workout. It does not automatically replace your exercise log.</p><SubsystemResponse subsystem="routine_maker" content={routine.generated} /></section>}
    <div className="day-tabs" role="tablist" aria-label="Workout days">{displayed.days.map((item, index) => <button key={item.name} role="tab" aria-selected={index === dayIndex} onClick={() => setDayIndex(index)}><span>DAY 0{index + 1}</span><strong>{item.name}</strong><small>{item.focus}</small></button>)}</div>
    <section className="workout-card">
      <div className="workout-heading"><div><span className="eyebrow">{['MONDAY', 'WEDNESDAY', 'FRIDAY'][dayIndex]}, LET&apos;S DO THIS</span><h2>{day.name} day <span>{day.exercises.length} exercises</span></h2></div>{editing ? <div className="button-group"><button className="text-button" onClick={() => { setEditing(false); setValidation('') }}>Cancel</button><button className="primary-button" onClick={saveEdits}><Check size={15} />Save changes</button></div> : <button className="secondary-button" onClick={() => { setDraft(structuredClone(routine)); setEditing(true) }}>Edit workout</button>}</div>
      <div className="workout-progress"><span style={{ width: `${complete / day.exercises.length * 100}%` }} /></div>
      <div className="exercise-table"><div className="exercise-table-head"><span>EXERCISE</span><span>SETS</span><span>REPS</span><span>KG</span><span>DONE</span></div>
        {day.exercises.map((exercise, index) => <div className={`exercise-row ${exercise.completed ? 'completed' : ''}`} key={exercise.name}><div className="exercise-name"><span className="exercise-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{exercise.name}</strong><small>{exercise.muscle} · {exercise.rest} rest</small></span></div>{['sets', 'reps', 'weight'].map((field) => <span key={field}>{editing ? <input aria-label={`${exercise.name} ${field}`} type={field === 'reps' ? 'text' : 'number'} min={field === 'sets' ? 1 : 0} max={field === 'sets' ? 10 : undefined} step={field === 'weight' ? 0.5 : 1} value={exercise[field]} onChange={(event) => changeExercise(index, field, event.target.value)} /> : exercise[field]}</span>)}<button className={`completion-button ${exercise.completed ? 'checked' : ''}`} aria-label={`Mark ${exercise.name} ${exercise.completed ? 'incomplete' : 'complete'}`} aria-pressed={exercise.completed} disabled={editing} onClick={() => { const next = { ...routine, days: routine.days.map((item, i) => i === dayIndex ? { ...item, exercises: item.exercises.map((entry, j) => j === index ? { ...entry, completed: !entry.completed } : entry) } : item) }; setRoutine(next); onSave(next) }}><Check size={15} /></button></div>)}
      </div>
      <div className="workout-footer"><span><CheckCheck size={17} />{complete} of {day.exercises.length} exercises completed</span><span>Warm up before you start. Make every rep count.</span></div>
    </section>
    {(validation || error) && <p role="alert" className="error-message">{validation || error}</p>}
    {saved && <p className="save-message" role="status"><Check size={15} />Changes saved on this device.</p>}
    <div className="routine-coach-banner"><span className="tip-icon"><Sparkles size={24} /></span><div><h3>Your routine isn&apos;t set in stone.</h3><p>Different schedule? New goal? Your coach can help you adapt.</p></div><button className="secondary-button" onClick={() => onAsk('Help me update my routine to fit my schedule.')}>Adjust with AI <ArrowRight size={16} /></button></div>
  </div>
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
      <p>Demo mode uses illustrative answers. Live API sends English requests to the backend. The endpoint is stateless: include any relevant history or routine in your message.</p>
      <p>My Routine is an editable demo workout. Your sets, weights, completion, and saved coach recommendation stay on this device. Specialist responses currently use Markdown; custom subsystem templates can be added later.</p>
      <button className="primary-button" onClick={onClose}>Got it <ArrowRight size={16} /></button>
    </section>
  </dialog>
}

function App() {
  const [restored] = useState(loadRoutine)
  const [tab, setTab] = useState('chat')
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [demo, setDemo] = useState(true)
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
      const result = demo ? await demoReply(query, controller.signal) : await requestChat(query, sessionId, controller.signal)
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', ...result, demo }])
    } catch (requestError) {
      if (requestError.name !== 'AbortError') setError(`${requestError.message} Your message was not answered. You can retry it below.`)
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
      <header className="topbar"><div className="breadcrumbs">Your workspace<ChevronRight size={14} /><strong>{tab === 'chat' ? 'AI Chat' : 'My Routine'}</strong></div><div className="topbar-right"><span className="private-label"><span className="status-dot" />Your space to grow</span><label className="mode-switch"><select aria-label="Chat connection mode" value={demo ? 'demo' : 'live'} disabled={pending} onChange={(event) => { setDemo(event.target.value === 'demo'); setError('') }}><option value="demo">Demo mode</option><option value="live">Live API</option></select><ChevronDown size={12} /></label><span className="header-avatar">JD</span></div></header>
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
            {pending && <article className="message assistant"><div className="message-avatar"><BrandMark small /></div><div className="message-body"><div className="message-heading"><strong>Form coach</strong><span>Working on it…</span></div><Pipeline pending demo={demo} /></div></article>}
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

export default App
