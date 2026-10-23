import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { ErrorNote, Logo } from '../ui'

/** The page a reset email links to. The token is single-use and expires in 30 minutes. */
export default function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [pw, setPw] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault(); setError(null)
    if (pw !== again) { setError('The two passwords do not match.'); return }
    setBusy(true)
    try { await api.reset(token, pw); setDone(true) } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  return (
    <>
      <header className="topbar"><Link to="/"><Logo /></Link></header>
      <div style={{ maxWidth: 440, margin: '56px auto', padding: '0 22px' }}>
        <div className="panel">
          {done ? <>
            <h1 className="form-title">Password changed</h1>
            <p className="form-sub">You can now sign in with your new password.</p>
            <Link className="btn btn-primary btn-full" to="/login">Go to log in</Link>
          </> : !token ? <>
            <h1 className="form-title">This link is incomplete</h1>
            <p className="form-sub">Open the link from your email again, or request a new one from the log in screen.</p>
            <Link className="btn btn-outline btn-full" to="/login">Back to log in</Link>
          </> : <form onSubmit={submit}>
            <h1 className="form-title">Choose a new password</h1>
            <p className="form-sub">At least 12 characters. This link works once.</p>
            <ErrorNote error={error} />
            <div className="field"><label htmlFor="np">New password</label>
              <input id="np" type="password" minLength={12} required autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></div>
            <div className="field"><label htmlFor="np2">Repeat it</label>
              <input id="np2" type="password" minLength={12} required autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} /></div>
            <button className="btn btn-primary btn-full" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button>
          </form>}
        </div>
      </div>
    </>
  )
}
