import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, dateFmt, daysUntil, KIND_LABEL, pretty, QUADRANT_COLOR, QUADRANT_LABEL, zar, type Kind, type PublicCard, type PublicPreview, type Role, type Taxonomy } from '../api'
import AuthModal from '../components/AuthModal'
import { Icon } from '../components/Icon'
import LxTop from '../components/LxTop'
import { useLoad } from '../hooks'
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
  const d = daysUntil(deadline)
  if (d === null) return <span className="lx-chip">Open</span>
  if (d < 0) return <span className="lx-chip">Closed</span>
  return <span className={`lx-chip ${d <= 7 ? 'hot' : ''}`}>{d === 0 ? 'Closes today' : `Closes in ${d} day${d === 1 ? '' : 's'}`}</span>
}

export function OppCard({ o }: { o: PublicCard }) {
  return (
    <Link to={`/opportunities/${o.id}`} className="lx-opp">
      <div className="lx-opp-top"><span className="lx-kind">{KIND_LABEL[o.kind]}</span><Closing deadline={o.deadline} /></div>
      <h3>{o.title}</h3>
      <p className="lx-opp-by">{o.provider} · {pretty(o.sector)} · {o.province}</p>
      <div className="lx-opp-foot"><b>{zar(o.contract_value)}</b><span>Check your fit <Icon name="arrow" size={15} /></span></div>
    </Link>
  )
}

export function PublicOpportunities() {
  const gate = useGate()
  const list = useLoad(() => api.publicOpportunities())
  const [kind, setKind] = useState<Kind | 'all'>('all')
  const [q, setQ] = useState('')
  const shown = useMemo(() => (list.data ?? []).filter((o) =>
    (kind === 'all' || o.kind === kind) && `${o.title} ${o.provider} ${o.sector} ${o.province}`.toLowerCase().includes(q.toLowerCase())), [list.data, kind, q])
  const kinds = Array.from(new Set((list.data ?? []).map((o) => o.kind)))
  return (
    <div className="lx lx-page">
      <LxTop onLogin={() => gate.open('login')} onSignup={() => gate.open('signup')} />
      <main className="lx-wrap">
        <span className="lx-eyebrow">Open to everyone</span>
        <h1 className="lx-h1">Opportunities you can check <em>before you sign up.</em></h1>
        <p className="lx-lead">Browse what is on offer, then see in seconds how the platform would judge your business.</p>
        <div className="lx-filters">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name, buyer, sector or province" aria-label="Search" />
          <div>{(['all', ...kinds] as (Kind | 'all')[]).map((k) => <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{k === 'all' ? 'All' : KIND_LABEL[k]}</button>)}</div>
        </div>
        {list.loading && <Spinner />}
        <div className="lx-grid">{shown.map((o) => <OppCard key={o.id} o={o} />)}</div>
        {!list.loading && shown.length === 0 && <p className="lx-lead">Nothing matches that search.</p>}
      </main>
      {gate.modal}
    </div>
  )
}

const DOC_CHOICES = ['TCS', 'BBBEE', 'COID', 'CSD', 'CIDB']

export function PublicOpportunity() {
  const { id = '' } = useParams()
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

  const key = JSON.stringify(f)
  useEffect(() => {
    if (!opp.data || !f.sector || !f.province || f.turnover <= 0) return
    const t = setTimeout(() => {
      setBusy(true)
      api.publicPreview(id, { sector: f.sector, province: f.province, years_trading: f.years, annual_turnover: f.turnover, capability_codes: f.caps, documents: f.docs })
        .then((r) => { setRes(r); setErr(null) }).catch((e: Error) => setErr(e.message)).finally(() => setBusy(false))
    }, 350)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, opp.data?.id])

  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])
  const caps = tax?.capabilities ?? []
  const o = opp.data
  return (
    <div className="lx lx-page">
      <LxTop onLogin={() => gate.open('login')} onSignup={() => gate.open('signup')} />
      <main className="lx-wrap">
        <Link to="/opportunities" className="lx-back">← All opportunities</Link>
        {opp.loading && <Spinner />}
        {opp.error && <p className="lx-lead">This opportunity is not open any more.</p>}
        {o && <div className="lx-detail">
          <section className="lx-card-d">
            <div className="lx-opp-top"><span className="lx-kind">{KIND_LABEL[o.kind]}</span><Closing deadline={o.deadline} /></div>
            <h1 className="lx-h1 small">{o.title}</h1>
            <p className="lx-opp-by">{o.provider} · {pretty(o.sector)} · {o.province}{o.deadline ? ` · closes ${dateFmt(o.deadline)}` : ''}</p>
            <div className="lx-value"><small>Contract value</small><b>{zar(o.contract_value)}</b><span>{o.duration_months} months · paid in {o.payment_terms_days} days</span></div>
            {o.description && <p className="lx-desc">{o.description}</p>}
            <h3>The work</h3>
            {o.scope.map((s) => <div key={s.label} className="lx-line"><span>{s.label}</span><b>{zar(s.value)}</b></div>)}
            <h3>What the buyer asks for</h3>
            {o.requirements.map((r, i) => (
              <div key={i} className="lx-line"><span>{r.text}{r.days ? <small> · {r.days} days{r.cost_zar ? `, ${zar(r.cost_zar)}` : ', free'}</small> : null}</span>
                <em className={r.mandatory ? 'must' : ''}>{r.mandatory ? 'Required' : 'Preferred'}</em></div>))}
            {o.preference.length > 0 && <p className="lx-note">The buyer also prefers {o.preference.map((p) => p.replace('_', ' ')).join(', ')}-owned businesses. It is shown on the match, and capped at 10 fit points.</p>}
          </section>

          <aside className="lx-check">
            <h2>Would you win this?</h2>
            <p className="hint">Answer five quick questions. We run the real scoring engine. Nothing is saved.</p>
            <div className="lx-form">
              <label>Sector<select value={f.sector} onChange={(e) => setF({ ...f, sector: e.target.value })}>{(tax?.sectors ?? [o.sector]).map((s) => <option key={s} value={s}>{pretty(s)}</option>)}</select></label>
              <label>Province<select value={f.province} onChange={(e) => setF({ ...f, province: e.target.value })}>{(tax?.provinces ?? [o.province]).map((s) => <option key={s}>{s}</option>)}</select></label>
              <label>Years trading<input type="number" min={0} max={100} value={f.years} onChange={(e) => setF({ ...f, years: Math.max(0, Number(e.target.value)) })} /></label>
              <label>Annual turnover (R)<input type="number" min={1} step={100000} value={f.turnover} onChange={(e) => setF({ ...f, turnover: Math.max(0, Number(e.target.value)) })} /></label>
            </div>
            <div className="lx-pick"><b>What you can do</b><div>{caps.filter((c) => c.sector === f.sector || f.caps.includes(c.code)).map((c) => <button key={c.code} className={f.caps.includes(c.code) ? 'on' : ''} onClick={() => setF({ ...f, caps: toggle(f.caps, c.code) })}>{c.label}</button>)}</div></div>
            <div className="lx-pick"><b>Documents you already hold</b><div>{DOC_CHOICES.map((c) => <button key={c} className={f.docs.includes(c) ? 'on' : ''} onClick={() => setF({ ...f, docs: toggle(f.docs, c) })}>{tax?.credentials.find((x) => x.code === c)?.label ?? c}</button>)}</div></div>

            <div className={`lx-result ${busy ? 'busy' : ''}`}>
              {err && <p className="lx-err">{err}</p>}
              {!res && !err && <Spinner />}
              {res && <>
                {res.gate === 'fail' ? <div className="lx-verdict"><b>Not eligible</b><p>{res.fail_reasons.join('. ')}.</p></div> : <>
                  <div className="lx-verdict">
                    <div className="lx-rings"><ScoreRing value={res.fit} label="Fit" /><ScoreRing value={res.readiness} label="Ready" color="#f59e0b" /></div>
                    <div><span className="lx-qpill" style={{ background: QUADRANT_COLOR[res.quadrant] }}>{QUADRANT_LABEL[res.quadrant]}</span>
                      {res.unlock.documents > 0
                        ? <p><b>{res.unlock.documents} document{res.unlock.documents > 1 ? 's' : ''} away.</b> About {res.unlock.days} days and {res.unlock.cost_zar ? zar(res.unlock.cost_zar) : 'no cost'} to be award ready.</p>
                        : <p><b>Nothing in your way.</b> You meet every mandatory requirement.</p>}</div>
                  </div>
                  {res.gaps.length > 0 && <div className="grid-gaps lx-gaps">{res.gaps.map((g) => <GapCard key={g.credential} g={g} />)}</div>}
                  <details className="lx-how"><summary>How the platform decided</summary>
                    <ol><li><b>Gate.</b> Hard requirements are checked first. Missing paperwork is coachable; a structural mismatch is not.</li>
                      <li><b>Fit.</b> Capability, capacity, location, experience and the buyer’s preference, by fixed weights.</li>
                      <li><b>Readiness.</b> Valid documents count in full, expired ones at 40%, missing ones at nothing.</li>
                      <li><b>Risk.</b> A warning if the contract is too large for your turnover.</li></ol>
                    <ScoreBreakdown components={res.components} />
                    <p className="hint">{res.summary}</p>
                  </details></>}
              </>}
            </div>
            <div className="lx-gate">
              <b>Want to apply, or keep this match up to date?</b>
              <p>Create a free account to apply, upload documents, get your passport, and watch this number drop as you close each gap.</p>
              <button className="lx-btn lx-btn-gold lx-btn-lg" onClick={() => gate.open('signup')}>Create a free account <Icon name="arrow" size={18} /></button>
              <button className="lx-link" onClick={() => gate.open('login')}>I already have an account</button>
            </div>
          </aside>
        </div>}
      </main>
      {gate.modal}
    </div>
  )
}
