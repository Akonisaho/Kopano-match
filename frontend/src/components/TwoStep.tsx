import { useState, type FormEvent } from 'react'
import { api, isProvider, type MfaSetup } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorNote, Panel, useToast } from '../ui'

/** Optional two-step sign-in with an authenticator app, plus one-time recovery codes. */
export default function TwoStep() {
  const { me, refresh } = useAuth()
  const toast = useToast()
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [codes, setCodes] = useState<string[] | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!me) return null
  const enabled = me.mfa_enabled
  const recommended = me.role === 'admin' || isProvider(me.role)

  async function run(action: () => Promise<void>) {
    setError(null); setBusy(true)
    try { await action() } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  const start = () => run(async () => setSetup(await api.mfaSetup()))
  const turnOn = (e: FormEvent) => { e.preventDefault(); run(async () => {
    setCodes((await api.mfaEnable(code)).recovery_codes); setSetup(null); setCode(''); await refresh()
    toast('Two-step sign-in is on.')
  }) }
  const turnOff = (e: FormEvent) => { e.preventDefault(); run(async () => {
    await api.mfaDisable(code); setCode(''); await refresh(); toast('Two-step sign-in is off.', 'info')
  }) }
  const download = () => {
    const url = URL.createObjectURL(new Blob([`Kopano Match recovery codes for ${me.email}\nEach code works once.\n\n${codes!.join('\n')}\n`], { type: 'text/plain' }))
    const a = document.createElement('a'); a.href = url; a.download = 'kopano-recovery-codes.txt'; a.click(); URL.revokeObjectURL(url)
  }

  return (
    <Panel title="Two-step sign-in" sub="A code from an authenticator app, on top of your password." right={<Badge tone={enabled ? 'green' : 'gray'}>{enabled ? 'On' : 'Off'}</Badge>}>
      <ErrorNote error={error} />
      {codes && (
        <div className="callout amber" style={{ marginTop: 0, marginBottom: 14 }}>
          <b>Save these recovery codes now.</b> Each works once if you lose your phone. They are not shown again.
          <div className="codes">{codes.map((c) => <code key={c}>{c}</code>)}</div>
          <div className="table-actions"><button className="btn btn-outline btn-small" onClick={download}>Download</button>
            <button className="btn btn-outline btn-small" onClick={() => setCodes(null)}>I have saved them</button></div>
        </div>)}
      {!enabled && !setup && <>
        <p style={{ fontSize: 13, color: '#475467', lineHeight: 1.6, marginTop: 0 }}>
          Works with Google Authenticator, Microsoft Authenticator, Authy and similar apps. The secret is stored encrypted.
          {recommended && ' Recommended for your role.'}</p>
        <button className="btn btn-primary" onClick={start} disabled={busy}>Set up two-step sign-in</button></>}
      {!enabled && setup && (
        <form onSubmit={turnOn}>
          <div className="mfa-setup">
            <img src={setup.qr} alt="QR code for your authenticator app" width={168} height={168} />
            <div>
              <p style={{ fontSize: 13, lineHeight: 1.6, margin: '0 0 8px' }}>1. Scan the code with your authenticator app, or type this key in:</p>
              <code className="secret">{setup.secret}</code>
              <p style={{ fontSize: 13, lineHeight: 1.6, margin: '12px 0 8px' }}>2. Enter the 6-digit code the app shows:</p>
              <div style={{ display: 'flex', gap: 10 }}>
                <input aria-label="6-digit code" inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456"
                  style={{ border: '1px solid #d7deea', borderRadius: 11, padding: '10px 13px', width: 150 }} />
                <button className="btn btn-primary" disabled={busy}>Turn on</button>
                <button type="button" className="btn btn-outline" onClick={() => { setSetup(null); setCode('') }}>Cancel</button>
              </div>
            </div>
          </div>
        </form>)}
      {enabled && (
        <form onSubmit={turnOff}>
          <p style={{ fontSize: 13, color: '#475467', lineHeight: 1.6, marginTop: 0 }}>To turn it off, enter a current code or one recovery code.</p>
          <div style={{ display: 'flex', gap: 10 }}>
            <input aria-label="Code to turn off" required value={code} onChange={(e) => setCode(e.target.value)} placeholder="Code"
              style={{ border: '1px solid #d7deea', borderRadius: 11, padding: '10px 13px', width: 170 }} />
            <button className="btn btn-danger" disabled={busy}>Turn off</button>
          </div>
        </form>)}
    </Panel>
  )
}
