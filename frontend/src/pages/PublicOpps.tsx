import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, dateFmt, daysUntil, KIND_LABEL, pretty, QUADRANT_COLOR, QUADRANT_LABEL, zar, type Kind, type PublicCard, type PublicPreview, type Role, type Taxonomy } from '../api'
import AuthModal from '../components/AuthModal'
import { Icon } from '../components/Icon'
import LxTop from '../components/LxTop'
import { ReadAloud, VoiceButton } from '../components/Voice'
import { useLoad } from '../hooks'
import { useLang, useT } from '../i18n'
import { ROLES } from '../roles'
import { GapCard, ScoreBreakdown, ScoreRing, Spinner } from '../ui'

/** The sign-up wall lives here: browsing and checking are free, acting needs an account. */
function useGate() {
  const [auth, setAuth] = useState<'login' | 'signup' | null>(null)
  const [role, setRole] = useState<Exclude<Role, 'admin'>>('sme')
  const modal = auth && <AuthModal mode={auth} role={role} roles={ROLES} setMode={setAuth} setRole={setRole} onClose={() => setAuth(null)} />
  return { open: (m: 'login' | 'signup') => setAuth(m), modal }
}

function Closing({ deadline }: { deadline: string | null }) {
  const t = useT()
  const d = daysUntil(deadline)
  if (d === null) return <span className="lx-chip">{t('Open')}</span>
  if (d < 0) return <span className="lx-chip">{t('Closed')}</span>
  return <span className={`lx-chip ${d <= 7 ? 'hot' : ''}`}>{d === 0 ? t('Closes today') : d === 1 ? t('Closes in 1 day') : t('Closes in {n} days', { n: d })}</span>
}

export function OppCard({ o }: { o: PublicCard }) {
  const t = useT()
  return (
    <Link to={`/opportunities/${o.id}`} className="lx-opp">
      <div className="lx-opp-top"><span className="lx-kind">{t(KIND_LABEL[o.kind])}</span><Closing deadline={o.deadline} /></div>
      <h3>{o.title}</h3>
      <p className="lx-opp-by">{o.provider} · {t(pretty(o.sector))} · {o.province}</p>
      <div className="lx-opp-foot"><b>{zar(o.contract_value)}</b><span>{t('Check your fit')} <Icon name="arrow" size={15} /></span></div>
    </Link>
  )
}

const KIND_ORDER: Kind[] = ['procurement', 'grant', 'funding', 'training', 'support']
type Sort = 'closing' | 'value'

export function PublicOpportunities() {
  const t = useT()
  const gate = useGate()
  const list = useLoad(() => api.publicOpportunities())
  const [kind, setKind] = useState<Kind | 'all'>('all')
  const [q, setQ] = useState('')
  const [sector, setSector] = useState('')
  const [province, setProvince] = useState('')
  const [soon, setSoon] = useState(false)
  const [sort, setSort] = useState<Sort>('closing')
  const all = list.data ?? []
  const count = (k: Kind) => all.filter((o) => o.kind === k).length
  const sectors = Array.from(new Set(all.map((o) => o.sector))).sort()
  const provinces = Array.from(new Set(all.map((o) => o.province))).sort()
  const shown = useMemo(() => {
    const rows = all.filter((o) =>
      (kind === 'all' || o.kind === kind) && (!sector || o.sector === sector) && (!province || o.province === province)
      && (!soon || (daysUntil(o.deadline) ?? 999) <= 14)
      && `${o.title} ${o.provider} ${o.sector} ${o.province}`.toLowerCase().includes(q.toLowerCase()))
    const far = '9999-12-31'
    return rows.sort((a, b) => sort === 'value' ? b.contract_value - a.contract_value : (a.deadline ?? far).localeCompare(b.deadline ?? far))
  }, [all, kind, q, sector, province, soon, sort])
  const filtered = kind !== 'all' || sector || province || soon || q
  return (
    <div className="lx lx-page">
      <LxTop onLogin={() => gate.open('login')} onSignup={() => gate.open('signup')} />
      <main className="lx-wrap">
        <span className="lx-eyebrow">{t('Open to everyone')}</span>
        <h1 className="lx-h1">{t('Opportunities you can check')} <em>{t('before you sign up.')}</em></h1>
        <p className="lx-lead">{t('Contracts, grants, funding, training and support. See in seconds how the platform would judge your business.')}</p>
        <div className="lx-types" role="tablist" aria-label={t('Type')}>
          <button className={kind === 'all' ? 'on' : ''} onClick={() => setKind('all')}>{t('All')} <i>{all.length}</i></button>
          {KIND_ORDER.map((k) => (
            <button key={k} className={`${kind === k ? 'on' : ''} ${count(k) === 0 ? 'empty' : ''}`} onClick={() => setKind(k)}>{t(KIND_LABEL[k])} <i>{count(k)}</i></button>))}
        </div>
        <div className="lx-filters">
          <span className="lx-search">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('Search by name, corporate, sector or province')} aria-label={t('Search')} />
            <VoiceButton onText={setQ} />
          </span>
          <select value={sector} onChange={(e) => setSector(e.target.value)} aria-label={t('Sector')}><option value="">{t('All sectors')}</option>{sectors.map((s) => <option key={s} value={s}>{t(pretty(s))}</option>)}</select>
          <select value={province} onChange={(e) => setProvince(e.target.value)} aria-label={t('Province')}><option value="">{t('All provinces')}</option>{provinces.map((s) => <option key={s}>{s}</option>)}</select>
          <button className={soon ? 'on' : ''} onClick={() => setSoon(!soon)}>{t('Closing soon')}</button>
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label={t('Sort')}><option value="closing">{t('Closing soonest')}</option><option value="value">{t('Highest value')}</option></select>
          {filtered && <button className="lx-clear" onClick={() => { setKind('all'); setQ(''); setSector(''); setProvince(''); setSoon(false) }}>{t('Clear')}</button>}
        </div>
        {list.loading && <Spinner />}
        <p className="lx-count-line">{shown.length === 1 ? t('1 opportunity') : t('{n} opportunities', { n: shown.length })}</p>
        <div className="lx-grid">{shown.map((o) => <OppCard key={o.id} o={o} />)}</div>
        {!list.loading && shown.length === 0 && <p className="lx-lead">{t('Nothing matches those filters.')}</p>}
      </main>
      {gate.modal}
    </div>
  )
}

type PublicDetailReq = { text: string; mandatory: boolean; kind: string; value: Record<string, unknown> }
const DOC_CHOICES = ['TCS', 'BBBEE', 'COID', 'CSD', 'CIDB']

export function PublicOpportunity() {
  const { id = '' } = useParams()
  const t = useT()
  const { lang } = useLang()
  const gate = useGate()
  const opp = useLoad(() => api.publicOpportunity(id), [id])
  const [tax, setTax] = useState<Taxonomy | null>(null)
  const [f, setF] = useState({ sector: '', province: '', years: 5, turnover: 2000000, caps: [] as string[], docs: [] as string[] })
  const [res, setRes] = useState<PublicPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.taxonomy().then(setTax).catch(() => setTax(null)) }, [])
  useEffect(() => {
    if (opp.data && !f.sector) setF((x) => ({ ...x, sector: opp.data!.sector, province: opp.data!.province }))
  }, [opp.data, f.sector])

  const key = JSON.stringify(f) + lang
  useEffect(() => {
    if (!opp.data || !f.sector || !f.province || f.turnover <= 0) return
    const timer = setTimeout(() => {
      setBusy(true)
      api.publicPreview(id, { sector: f.sector, province: f.province, years_trading: f.years, annual_turnover: f.turnover, capability_codes: f.caps, documents: f.docs, language: lang })
        .then((r) => { setRes(r); setErr(null) }).catch((e: Error) => setErr(e.message)).finally(() => setBusy(false))
    }, 350)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, opp.data?.id])

  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])
  const caps = tax?.capabilities ?? []
  const o = opp.data
  /** A requirement in the reader's language, built from its values so the words are exact. */
  const reqText = (r: PublicDetailReq) => {
    const v = r.value
    if (r.kind === 'capability') { const c = caps.find((x) => x.code === v.code); if (c) return t('Can deliver {x}', { x: t(c.label).toLowerCase() }) }
    if (r.kind === 'compliance_doc' || r.kind === 'certification') { const c = tax?.credentials.find((x) => x.code === v.doc); if (c) return t('{label} from {issuer}', { label: t(c.label), issuer: t(c.issuer) }) }
    if (r.kind === 'min_years') return t('At least {n} years trading', { n: String(v.years) })
    if (r.kind === 'min_turnover') return t('Annual turnover of at least R{n}', { n: Number(v.amount).toLocaleString('en-ZA') })
    if (r.kind === 'province') return t('Based in {p}', { p: String(v.province) })
    return r.text
  }
  return (
    <div className="lx lx-page">
      <LxTop onLogin={() => gate.open('login')} onSignup={() => gate.open('signup')} />
      <main className="lx-wrap">
        <Link to="/opportunities" className="lx-back">← {t('All opportunities')}</Link>
        {opp.loading && <Spinner />}
        {opp.error && <p className="lx-lead">{t('This opportunity is not open any more.')}</p>}
        {o && <div className="lx-detail">
          <section className="lx-card-d">
            <div className="lx-opp-top"><span className="lx-kind">{t(KIND_LABEL[o.kind])}</span><Closing deadline={o.deadline} /></div>
            <h1 className="lx-h1 small">{o.title}</h1>
            <p className="lx-opp-by">{o.provider} · {t(pretty(o.sector))} · {o.province}{o.deadline ? ` · ${t('closes')} ${dateFmt(o.deadline)}` : ''}</p>
            <div className="lx-value"><small>{t('Contract value')}</small><b>{zar(o.contract_value)}</b><span>{t('{m} months · paid in {d} days', { m: o.duration_months, d: o.payment_terms_days })}</span></div>
            {o.description && <p className="lx-desc">{o.description}</p>}
            <h3>{t('The work')}</h3>
            {o.scope.map((s) => <div key={s.label} className="lx-line"><span>{t(s.label)}</span><b>{zar(s.value)}</b></div>)}
            <h3>{t('What the corporate asks for')}</h3>
            {o.requirements.map((r, i) => (
              <div key={i} className="lx-line"><span>{reqText(r)}{r.days ? <small> · {t('{n} days', { n: r.days })}{r.cost_zar ? `, ${zar(r.cost_zar)}` : `, ${t('free')}`}</small> : null}</span>
                <em className={r.mandatory ? 'must' : ''}>{r.mandatory ? t('Required') : t('Preferred')}</em></div>))}
            {o.preference.length > 0 && <p className="lx-note">{t('The corporate also prefers {who}-owned businesses. It is shown on the match, and capped at 10 fit points.', { who: o.preference.map((p) => p.replace('_', ' ')).join(', ') })}</p>}
          </section>

          <aside className="lx-check">
            <h2>{t('Would you win this?')}</h2>
            <p className="hint">{t('Answer five quick questions. We run the real scoring engine. Nothing is saved.')}</p>
            <div className="lx-form">
              <label>{t('Sector')}<select value={f.sector} onChange={(e) => setF({ ...f, sector: e.target.value })}>{(tax?.sectors ?? [o.sector]).map((s) => <option key={s} value={s}>{t(pretty(s))}</option>)}</select></label>
              <label>{t('Province')}<select value={f.province} onChange={(e) => setF({ ...f, province: e.target.value })}>{(tax?.provinces ?? [o.province]).map((s) => <option key={s}>{s}</option>)}</select></label>
              <label>{t('Years trading')}<input type="number" min={0} max={100} value={f.years} onChange={(e) => setF({ ...f, years: Math.max(0, Number(e.target.value)) })} /></label>
              <label>{t('Annual turnover (R)')}<input type="number" min={1} step={100000} value={f.turnover} onChange={(e) => setF({ ...f, turnover: Math.max(0, Number(e.target.value)) })} /></label>
            </div>
            <div className="lx-pick"><b>{t('What you can do')}</b><div>{caps.filter((c) => c.sector === f.sector || f.caps.includes(c.code)).map((c) => <button key={c.code} className={f.caps.includes(c.code) ? 'on' : ''} onClick={() => setF({ ...f, caps: toggle(f.caps, c.code) })}>{t(c.label)}</button>)}</div></div>
            <div className="lx-pick"><b>{t('Documents you already hold')}</b><div>{DOC_CHOICES.map((c) => <button key={c} className={f.docs.includes(c) ? 'on' : ''} onClick={() => setF({ ...f, docs: toggle(f.docs, c) })}>{t(tax?.credentials.find((x) => x.code === c)?.label ?? c)}</button>)}</div></div>

            <div className={`lx-result ${busy ? 'busy' : ''}`}>
              {err && <p className="lx-err">{err}</p>}
              {!res && !err && <Spinner />}
              {res && <>
                {res.gate === 'fail' ? <div className="lx-verdict"><b>{t('Not eligible')}</b><p>{res.fail_reasons.join('. ')}.</p></div> : <>
                  <div className="lx-verdict">
                    <div className="lx-rings"><ScoreRing value={res.fit} label={t('Fit')} /><ScoreRing value={res.readiness} label={t('Ready')} color="#f59e0b" /></div>
                    <div><span className="lx-qpill" style={{ background: QUADRANT_COLOR[res.quadrant] }}>{t(QUADRANT_LABEL[res.quadrant])}</span>
                      {res.unlock.documents > 0
                        ? <p><b>{res.unlock.documents === 1 ? t('1 document away.') : t('{n} documents away.', { n: res.unlock.documents })}</b> {t('About {d} days and {c} to be award ready.', { d: res.unlock.days, c: res.unlock.cost_zar ? zar(res.unlock.cost_zar) : t('no cost') })}</p>
                        : <p><b>{t('Nothing in your way.')}</b> {t('You meet every mandatory requirement.')}</p>}
                      <ReadAloud text={res.summary} /></div>
                  </div>
                  {res.gaps.length > 0 && <div className="grid-gaps lx-gaps">{res.gaps.map((g) => <GapCard key={g.credential} g={g} />)}</div>}
                  <details className="lx-how"><summary>{t('How the platform decided')}</summary>
                    <ol><li><b>{t('Gate.')}</b> {t('Hard requirements are checked first. Missing paperwork is coachable; a structural mismatch is not.')}</li>
                      <li><b>{t('Fit.')}</b> {t('Capability, capacity, location, experience and the corporate’s preference, by fixed weights.')}</li>
                      <li><b>{t('Readiness.')}</b> {t('Valid documents count in full, expired ones at 40%, missing ones at nothing.')}</li>
                      <li><b>{t('Risk.')}</b> {t('A warning if the contract is too large for your turnover.')}</li></ol>
                    <ScoreBreakdown components={res.components} />
                    <p className="hint">{res.summary}</p>
                  </details></>}
              </>}
            </div>
            <div className="lx-gate">
              <b>{t('Want to apply, or keep this match up to date?')}</b>
              <p>{t('Create a free account to apply, upload documents, get your passport, and watch this number drop as you close each gap.')}</p>
              <button className="lx-btn lx-btn-gold lx-btn-lg" onClick={() => gate.open('signup')}>{t('Create a free account')} <Icon name="arrow" size={18} /></button>
              <button className="lx-link" onClick={() => gate.open('login')}>{t('I already have an account')}</button>
            </div>
          </aside>
        </div>}
      </main>
      {gate.modal}
    </div>
  )
}
