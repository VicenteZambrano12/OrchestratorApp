import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import { listUsers, registerUser } from '../../hooks/session/users'

export default function UserDialog({ user, onSwitch, onClose }) {
  const { t } = useTranslation()
  const dialogRef = useRef(null)
  const controllerRef = useRef(null)
  const [users, setUsers] = useState([])
  const [selected, setSelected] = useState(String(user.id))
  const [username, setUsername] = useState('')
  const [weightUnit, setWeightUnit] = useState('kg')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const dialog = dialogRef.current
    dialog.showModal()
    return () => { dialog.close(); controllerRef.current?.abort() }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    listUsers(controller.signal).then((result) => {
      if (!controller.signal.aborted) { setUsers(result); setLoading(false) }
    }).catch((error) => {
      if (!controller.signal.aborted) { setError(error.message); setLoading(false) }
    })
    return () => controller.abort()
  }, [attempt])

  async function submit(event, create) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    const controller = new AbortController()
    controllerRef.current = controller
    try {
      const next = create
        ? await registerUser(username, weightUnit, controller.signal)
        : users.find((candidate) => String(candidate.id) === selected)
      if (!next) throw new Error('Select a user.')
      // Keep a newly registered profile available if session activation fails.
      if (create) {
        setUsers((current) => [...current, next])
        setSelected(String(next.id))
        setUsername('')
      }
      await onSwitch(next, controller.signal)
      if (!controller.signal.aborted) onClose()
    } catch (error) {
      if (!controller.signal.aborted) setError(error.message)
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <dialog ref={dialogRef} className="help-dialog" aria-labelledby="user-title"
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose() }}
    onClick={(event) => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <section className="help-modal user-modal" aria-busy={busy || loading}>
      <button className="icon-button modal-close" aria-label={t('Close user selection')} disabled={busy} onClick={onClose}><X size={20} /></button>
      <h2 id="user-title">{t('Choose your user')}</h2>
      <p>{t('Profiles are local users, not password-protected accounts.')}</p>
      <form onSubmit={(event) => submit(event, false)}>
        <label htmlFor="existing-user">{t('User')}</label>
        <select id="existing-user" value={selected} onChange={(event) => setSelected(event.target.value)} disabled={busy || loading}>
          {users.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.username}</option>)}
        </select>
        <button className="primary-button" disabled={busy || loading || !users.length}>{t('Switch user')}</button>
      </form>
      <form onSubmit={(event) => submit(event, true)}>
        <h3>{t('Register a new user')}</h3>
        <label htmlFor="new-username">{t('Username')}</label>
        <input id="new-username" value={username} onChange={(event) => setUsername(event.target.value)} required maxLength={80} disabled={busy || loading} autoComplete="off" />
        <label htmlFor="weight-unit">{t('Weight unit')}</label>
        <select id="weight-unit" value={weightUnit} onChange={(event) => setWeightUnit(event.target.value)} disabled={busy || loading}>
          <option value="kg">kg</option><option value="lbs">lbs</option>
        </select>
        <button className="primary-button" disabled={busy || loading || !username.trim()}>{t('Register and switch')}</button>
      </form>
      {loading && <p role="status">{t('Loading…')}</p>}
      {error && <div role="alert"><p>{t('Could not update user: {{message}}', { message: t(error) })}</p>
        {!users.length && <button className="secondary-button" disabled={loading} onClick={() => { setError(''); setLoading(true); setAttempt((n) => n + 1) }}>{t('Retry')}</button>}
      </div>}
    </section>
  </dialog>
}
