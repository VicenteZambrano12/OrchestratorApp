import { RotateCcw } from 'lucide-react'

function FailingView({ onRetry }) {
  return (
    <main role="alert" style={{ minHeight: '100vh', display: 'grid', placeContent: 'center', gap: '1rem', textAlign: 'center', padding: '2rem' }}>
      <h1>Backend unavailable</h1>
      <p>We couldn’t reach the server. Make sure the backend is running and try again.</p>
      <button type="button" onClick={onRetry} style={{ justifySelf: 'center', display: 'inline-flex', gap: '.5rem', alignItems: 'center', cursor: 'pointer' }}>
        <RotateCcw size={16} /> Retry
      </button>
    </main>
  )
}

export default FailingView
