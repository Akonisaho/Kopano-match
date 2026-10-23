import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Role } from '../api'
import { homeFor, useAuth } from '../auth'
import { ErrorNote, Logo, Modal, useToast } from '../ui'

export type RoleKey = Exclude<Role, 'admin'>
export interface RoleOption { key: RoleKey; label: string; desc: string }

type Step = 'form' | 'mfa' | 'forgot' | 'sent'

export default function AuthModal({ mode, role, roles, setMode, setRole, onClose }: {
  mode: 'login' | 'signup'; role: RoleKey; roles: RoleOption[]
  setMode: (m: 'login' | 'signup') => void; setRole: (r: RoleKey) => void; onClose: () => void
}) {
  const { signIn } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const [f, setF] = useState({ full_name: '', organisation_name: '', email: '', phone: '', password: '', registration_number: '' })
  const [consent, setConsent] = useState(false)
  const [step, setStep] = useState<Step>('form')
  const [mfaToken, setMfaToken] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  async function finish(token: string, welcome: string) {
    const m = await signIn(token)
    onClose()
    toast(welcome)
    nav(homeFor(m.role))
  }

  async function run(action: () => Promise<void>) {
    setError(null); setBusy(true)
    try { await action() } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  const submit = (e: FormEvent) => { e.preventDefault(); run(async () => {
    if (mode === 'login') {
      const r = await api.login(f.email, f.password)
      if (r.mfa_required && r.mfa_token) { setMfaToken(r.mfa_token); setStep('mfa'); return }
      await finish(r.access_token!, 'Welcome back.')
    } else {
      const r = await api.register({ ...f, role, consent, phone: f.phone || null, registration_number: f.registration_number || null })
      await finish(r.access_token!, 'Account created. Check your inbox for a welcome email.')
    }
  }) }

  const verify = (e: FormEvent) => { e.preventDefault(); run(async () => {
    const r = await api.mfaVerify(mfaToken, code)
    await finish(r.access_token, 'Welcome back.')
  }) }

  const forgot = (e: FormEvent) => { e.preventDefault(); run(async () => { await api.forgot(f.email); setStep('sent') }) }

  return (
    <Modal onClose={onClose}>
      <div className="auth-layout">
        <div className="auth-brand">
          <Logo dark />
          <h2>Join a trusted opportunity ecosystem.</h2>
          <p>Verified profiles. Real opportunities. Explainable matching. Human-reviewed trust decisions.</p>
          <div className="auth-benefits">
            <span><i />Fit and readiness, never one opaque score</span><span><i />Costed, dated plans to close every gap</span>
            <span><i />Identity images are never stored</span><span><i />An audit trail the app cannot rewrite</span>
          </div>
        </div>
        <div className="auth-form">
          {step === 'form' && <div className="auth-tabs">
            <button className={mode === 'signup' ? 'active' : ''} onClick={() => { setError(null); setMode('signup') }}>Create account</button>
            <button className={mode === 'login' ? 'active' : ''} onClick={() => { setError(null); setMode('login') }}>Log in</button>
          </div>}

          {step === 'mfa' && <form onSubmit={verify}>
            <h3 className="form-title">Two-step sign-in</h3>
            <p className="form-sub">Open your authenticator app and enter the 6-digit code for Kopano Match. Lost your phone? Use one of your recovery codes instead.</p>
            <ErrorNote error={error} />
            <div className="field"><label htmlFor="mfa">Code</label>
              <input id="mfa" inputMode="text" autoComplete="one-time-code" autoFocus required value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456" /></div>
            <button className="btn btn-primary btn-full" disabled={busy}>{busy ? 'Checking…' : 'Verify and sign in'}</button>
            <button type="button" className="btn btn-ghost btn-full" onClick={() => { setStep('form'); setCode(''); setError(null) }}>Back</button>
          </form>}

          {step === 'forgot' && <form onSubmit={forgot}>
            <h3 className="form-title">Reset your password</h3>
            <p className="form-sub">Enter your email. If an account exists, we send a single-use link that works for 30 minutes.</p>
            <ErrorNote error={error} />
            <div className="field"><label htmlFor="fe">Email address</label>
              <input id="fe" type="email" required autoFocus autoComplete="username" value={f.email} onChange={set('email')} /></div>
            <button className="btn btn-primary btn-full" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button>
            <button type="button" className="btn btn-ghost btn-full" onClick={() => { setStep('form'); setError(null) }}>Back to log in</button>
          </form>}

          {step === 'sent' && <div>
            <h3 className="form-title">Check your inbox</h3>
            <p className="form-sub">If that email is registered, a reset link is on its way. It works once and expires in 30 minutes. Check your spam folder if it does not arrive.</p>
            <button className="btn btn-outline btn-full" onClick={() => setStep('form')}>Back to log in</button>
          </div>}

          {step === 'form' && mode === 'signup' && <form onSubmit={submit}>
            <h3 className="form-title">Create your account</h3>
            <p className="form-sub">Choose your role first. Your workspace is tailored to it.</p>
            <div className="field"><span className="lbl">I am joining as</span>
              <div className="role-grid">{roles.map((r) => (
                <button type="button" key={r.key} className={`role-option ${role === r.key ? 'active' : ''}`} onClick={() => setRole(r.key)}><b>{r.label}</b><span>{r.desc.split('.')[0]}.</span></button>))}</div></div>
            <ErrorNote error={error} />
            <div className="form-grid">
              <div className="field"><label htmlFor="n">Full name</label><input id="n" required value={f.full_name} onChange={set('full_name')} /></div>
              <div className="field"><label htmlFor="o">Organisation</label><input id="o" required value={f.organisation_name} onChange={set('organisation_name')} /></div>
            </div>
            <div className="field"><label htmlFor="e">Email address</label><input id="e" type="email" required autoComplete="username" value={f.email} onChange={set('email')} placeholder="you@company.co.za" /></div>
            <div className="form-grid">
              <div className="field"><label htmlFor="r">Registration number</label><input id="r" value={f.registration_number} onChange={set('registration_number')} placeholder="2018/123456/07" />
                <span className="hint">Checked against a registry adapter (simulated in this pilot).</span></div>
              <div className="field"><label htmlFor="p">Password</label><input id="p" type="password" required minLength={12} maxLength={72} autoComplete="new-password" value={f.password} onChange={set('password')} placeholder="12 to 72 characters" /></div>
            </div>
            <label className="check-row"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>I have read the <a href="/privacy" target="_blank" rel="noreferrer" style={{ color: 'var(--purple)' }}>privacy notice</a> and consent to my information being processed as described.</span></label>
            <button className="btn btn-primary btn-full" disabled={!consent || busy}>{busy ? 'Creating…' : 'Create account'}</button>
            <p className="hint" style={{ marginTop: 12 }}>Platform reviewer accounts are invite-only.</p>
          </form>}

          {step === 'form' && mode === 'login' && <form onSubmit={submit}>
            <h3 className="form-title">Welcome back</h3>
            <p className="form-sub">Log in to your Kopano Match workspace.</p>
            <ErrorNote error={error} />
            <div className="field"><label htmlFor="le">Email address</label><input id="le" type="email" required autoComplete="username" value={f.email} onChange={set('email')} /></div>
            <div className="field"><label htmlFor="lp">Password</label><input id="lp" type="password" required autoComplete="current-password" value={f.password} onChange={set('password')} /></div>
            <button className="btn btn-primary btn-full" disabled={busy}>{busy ? 'Signing in…' : 'Log in'}</button>
            <button type="button" className="btn btn-ghost btn-full" onClick={() => { setError(null); setStep('forgot') }}>Forgot your password?</button>
          </form>}
        </div>
      </div>
    </Modal>
  )
}
