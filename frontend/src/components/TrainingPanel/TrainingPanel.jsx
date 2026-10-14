import { ArrowRight, Dumbbell, Sparkles, Target } from 'lucide-react'
import BrandMark from '../BrandMark/BrandMark'
import { getWeeklyProgress } from '../../features/TrainingPanel/weekly-progress/getWeeklyProgress'

export default function TrainingPanel({ routine, onOpen, onPrompt }) {
  const { completed, weekDays } = getWeeklyProgress(routine)
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
    <div className="week-card"><div><h4>Your weekly rhythm</h4><span>{completed} exercises logged</span></div><div className="week-days">{weekDays.map(({ label, isTrainingDay }, index) => <div key={index}><span>{label}</span><span className={isTrainingDay ? 'training-day' : ''}>{isTrainingDay ? <Dumbbell size={14} /> : '–'}</span></div>)}</div><p><span className="status-dot" />Train. Recover. Repeat.</p></div>
    <div className="coach-tip"><span className="tip-icon"><Sparkles size={18} /></span><div><h4>Small steps. Real progress.</h4><p>A good plan adapts to your life, not the other way around.</p><button onClick={() => onPrompt('How can I stay consistent with my training?')}>Let&apos;s talk about your goals <ArrowRight size={13} /></button></div></div>
    <div className="powered"><BrandMark small /><span>One coach. A team of specialists.</span></div>
  </aside>
}
