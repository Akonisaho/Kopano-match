import { useState, type FormEvent } from 'react'
import { api, type AssistResult } from '../api'
import { LANGS, useT, type Lang } from '../i18n'
import { Badge, ErrorNote, Panel, useToast } from '../ui'

/** A support programme signs a business up, with its consent. The business sets its own password. */
export function AssistPanel() {
  const t = useT()
  const toast = useToast()
  const [f, setF] = useState({ full_name: '', email: '', organisation_name: '', registration_number: '', language: 'en' as Lang, consent: false })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<AssistResult | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null)
    try {
      setDone(await api.assistBusiness({ ...f, registration_number: f.registration_number || null }))
      toast(t('The business has been emailed a link to choose its own password.'))
      setF({ full_name: '', email: '', organisation_name: '', registration_number: '', language: f.language, consent: false })
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  return (
    <Panel title={t('Help a business sign up')} sub={t('For businesses that cannot easily do this alone. They agree first, and they choose their own password.')}
      right={<Badge tone="purple">{t('Assisted')}</Badge>}>
      <form onSubmit={submit}>
        <ErrorNote error={error} />
        <div className="form-grid">
          <div className="field"><label htmlFor="as-n">{t('Owner’s name')}</label><input id="as-n" required minLength={2} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></div>
          <div className="field"><label htmlFor="as-e">{t('Their email')}</label><input id="as-e" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
          <div className="field"><label htmlFor="as-o">{t('Business name')}</label><input id="as-o" required minLength={2} value={f.organisation_name} onChange={(e) => setF({ ...f, organisation_name: e.target.value })} /></div>
          <div className="field"><label htmlFor="as-r">{t('Registration number (optional)')}</label><input id="as-r" value={f.registration_number} onChange={(e) => setF({ ...f, registration_number: e.target.value })} placeholder="2020/123456/07" /></div>
          <div className="field"><label htmlFor="as-l">{t('Their language')}</label>
            <select id="as-l" value={f.language} onChange={(e) => setF({ ...f, language: e.target.value as Lang })}>{LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}</select></div>
        </div>
        <label className="check-row" style={{ margin: '4px 0 14px' }}>
          <input type="checkbox" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} />
          <span>{t('The business has agreed to the privacy notice and asked me to help.')}</span>
        </label>
        <button className="btn btn-primary" disabled={busy || !f.consent}>{busy ? t('Setting up…') : t('Sign the business up')}</button>
      </form>
      {done && <div className="callout green" style={{ marginTop: 14 }}>
        <b>{t('Done.')}</b> {t('An email has gone to {email}.', { email: done.email })}
        {done.setup_link && <p className="hint" style={{ margin: '6px 0 0' }}>{t('Demo only: the link is shown here so the flow can be seen without an inbox.')} <a href={done.setup_link}>{t('Open it')}</a></p>}
      </div>}
    </Panel>
  )
}
