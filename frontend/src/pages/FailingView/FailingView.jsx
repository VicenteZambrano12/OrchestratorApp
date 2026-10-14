import { RotateCcw, ServerCrash } from 'lucide-react'

function FailingView({ onRetry }) {
  return (
    <main className="failing-view">
      <section className="failing-card" role="alert">
        <ServerCrash size={32} aria-hidden="true" />
        <h1>Backend unavailable</h1>
        <p>We couldn’t reach the server. Make sure the backend is running and try again.</p>
        <button type="button" className="retry-button" onClick={onRetry}>
          <RotateCcw size={16} aria-hidden="true" /> Retry
        </button>
      </section>
    </main>
  )
}

export default FailingView
