import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, zar, type Role, type Showcase } from '../api'
import { homeFor, useAuth } from '../auth'
import QuadrantChart from '../components/QuadrantChart'
import { TRUST } from '../trust'
import { Badge, ErrorNote, Logo, Modal, useToast } from '../ui'

const ROLES: { key: Exclude<Role, 'admin'>; label: string; desc: string; points: string[] }[] = [
  { key: 'sme', label: 'SME', desc: 'Build a verified capability profile, see exactly what stands between you and each opportunity, and apply.',
    points: ['Readiness gaps with days and rand cost', 'Apply to matched opportunities', 'Your data, exportable and erasable'] },
  { key: 'corporate', label: 'Corporate / Buyer', desc: 'Post procurement opportunities as rules, and review ranked, explainable SME matches.',
    points: ['Requirements as weighted rules', 'Capacity-risk flags on every match', 'Consortium proposals when no one SME fits'] },
  { key: 'funder', label: 'Funder / Investor', desc: 'Publish grants, funding and investment programmes and find investment-ready businesses.',
    points: ['Ownership and turnover gates', 'Shortlists with audit trail', 'Human decides, system explains'] },
  { key: 'support', label: 'Business Support', desc: 'Connect SMEs to accelerators, mentoring and development programmes.',
    points: ['Match on readiness, not just size', 'See common bottlenecks', 'Track who applied and why'] },
]

const DEMO = [
  ['SME (coachable)', 'sme-001@sme.demo'], ['SME (overtrading flag)', 'sme-003@sme.demo'],
  ['Corporate', 'corporate@kopano.demo'], ['Funder', 'funder@kopano.demo'],
  ['Business support', 'support@kopano.demo'], ['Platform reviewer', 'admin@kopano.demo'],
]

export default function Landing({ initialAuth }: { initialAuth?: 'login' | 'signup' }) {
  const [auth, setAuth] = useState<'login' | 'signup' | null>(initialAuth ?? null)
  const [role, setRole] = useState<Exclude<Role, 'admin'>>('sme')
  const [show, setShow] = useState<Showcase | null>(null)
  const [slide, setSlide] = useState(0)
  const { me } = useAuth()
  const nav = useNavigate()
  const open = (mode: 'login' | 'signup', r?: Exclude<Role, 'admin'>) => { if (r) setRole(r); setAuth(mode) }

  useEffect(() => { api.showcase().then(setShow).catch(() => setShow(null)) }, [])
  useEffect(() => {
    const t = setInterval(() => setSlide((s) => (s + 1) % 3), 6000)
    return () => clearInterval(t)
  }, [])

  const q = (name: string) => show?.chart?.dots.filter((d) => d.quadrant === name).length ?? 0

  return (
    <>
      <header className="topbar">
        <Logo />
        <nav className="topnav"><a href="#how">How it works</a><a href="#different">What's different</a><a href="#trust">Trust &amp; security</a><a href="#users">Who it serves</a></nav>
        <div className="top-actions">
          {me ? <button className="btn btn-primary" onClick={() => nav(homeFor(me.role))}>Open workspace</button> : <>
            <button className="btn btn-ghost" onClick={() => open('login')}>Log in</button>
            <button className="btn btn-primary" onClick={() => open('signup')}>Create account</button></>}
        </div>
      </header>

      <main>
        <section className="hero">
          <div>
            <span className="eyebrow">Verified SME opportunity ecosystem</span>
            <h1>The right SME.<br />The right opportunity.<br /><span>Ready to award.</span></h1>
            <p>Kopano Match connects verified SMEs with procurement, funding, investment and business-support opportunities. Every match shows two things a single score hides: how well the business fits, and how ready it is, with the exact days and rand it takes to close each gap.</p>
            <div className="hero-actions">
              <button className="btn btn-primary" onClick={() => open('signup')}>Join Kopano Match</button>
              <a className="btn btn-outline" href="#different">See what's different</a>
            </div>
            <div className="trust-line"><span>Rules, not black-box scores</span><span>Costed readiness plans</span><span>Human-reviewed risk flags</span><span>Append-only audit trail</span></div>
          </div>

          <div className="hero-stage" aria-live="off">
            <div className={`hero-slide ${slide === 0 ? 'active' : ''}`}>
              <div className="hero-card">
                <small className="k">Live from the platform · {show?.chart ? zar(show.chart.contract_value) : 'procurement'} contract</small>
                <h3 style={{ margin: '4px 0 8px' }}>Fit and readiness, one dot per SME</h3>
                {show?.chart ? <QuadrantChart dots={show.chart.dots.map((d, i) => ({ key: String(i), ...d }))} /> : <p className="empty">Loading live data…</p>}
              </div>
            </div>
            <div className={`hero-slide ${slide === 1 ? 'active' : ''}`}>
              <div className="hero-card">
                <small className="k">Coachable, not discarded</small>
                <h3 style={{ margin: '4px 0 14px' }}>A conventional filter drops this business</h3>
                {show?.example ? <>
                  <div className="score-pair">
                    <Ring v={show.example.fit} label="Fit" color="#7c3aed" /><Ring v={show.example.readiness} label="Ready" color="#f59e0b" />
                    <div><b style={{ fontSize: 22, fontFamily: 'Manrope' }}>{show.example.days} days, {zar(show.example.cost_zar)}</b><p className="hint" style={{ margin: '4px 0 0' }}>stands between this SME and award</p></div>
                  </div>
                  <div style={{ display: 'grid', gap: 8, marginTop: 18 }}>
                    {show.example.gaps.map((g) => (
                      <div key={g.label} className="gap-card" style={{ padding: 12 }}>
                        <b style={{ fontSize: 13 }}>{g.label}</b>
                        <p>{g.issuer} · {g.days} days · {zar(g.cost_zar)} · also unlocks {g.also_unlocks} other</p>
                      </div>))}
                  </div></> : <p className="empty">Loading live data…</p>}
              </div>
            </div>
            <div className={`hero-slide ${slide === 2 ? 'active' : ''}`}>
              <div className="hero-card">
                <small className="k">When no single SME can deliver</small>
                <h3 style={{ margin: '4px 0 14px' }}>Consortium assembly</h3>
                {show?.consortium ? <>
                  <div className="stat-strip" style={{ marginTop: 0 }}>
                    <div><b>{show.consortium.members}</b><span>SMEs bundled</span></div>
                    <div><b>{show.consortium.scope_lines}</b><span>scope lines</span></div>
                    <div><b>{show.consortium.coverage_pct}%</b><span>covered</span></div>
                    <div><b>{zar(show.consortium.opportunity_value)}</b><span>contract</span></div>
                  </div>
                  <div className="callout blue">A greedy set-cover over the scope items bundles up to three SMEs and nominates the most ready as lead. No other SME fit this scope alone.</div></> : <p className="empty">Loading live data…</p>}
              </div>
            </div>
            <div className="hero-controls">{[0, 1, 2].map((i) => (
              <button key={i} className={`hero-dot ${slide === i ? 'active' : ''}`} onClick={() => setSlide(i)} aria-label={`Show slide ${i + 1}`} />))}</div>
          </div>
        </section>

        <section className="section white">
          <div className="stat-strip" style={{ maxWidth: 900, margin: '0 auto' }}>
            <div><b>{show?.smes ?? '–'}</b><span>SMEs on the platform</span></div>
            <div><b>{show?.opportunities ?? '–'}</b><span>open opportunities</span></div>
            <div><b>{q('award_now')}</b><span>award-ready on the featured contract</span></div>
            <div><b>{q('coachable')}</b><span>coachable on the featured contract</span></div>
          </div>
          <p className="hint" style={{ textAlign: 'center', marginTop: 12 }}>Counts above are read live from the platform's demo data.</p>
        </section>

        <section className="section" id="how">
          <div className="section-head"><span>HOW IT WORKS</span><h2>From verified profile to a decision you can defend</h2><p>One journey for SMEs and the organisations that source from them.</p></div>
          <div className="steps">
            {[['Profile', 'Structured capability profile: sector, province, turnover, capabilities. No free-text guesswork.'],
              ['Verify', 'Registry, tax and identity checks through provider adapters, with every source labelled.'],
              ['Match', 'A gate removes structural mismatches. Fit and readiness are scored by fixed rules.'],
              ['Improve', 'Every gap shows the issuer, days, rand cost and how many other opportunities it unlocks.'],
              ['Decide', 'A human shortlists. Every decision is written to a log the application cannot rewrite.']].map(([t, d], i) => (
              <div className="step" key={t}><b>{i + 1}</b><h3>{t}</h3><p>{d}</p></div>))}
          </div>
        </section>

        <section className="section white" id="different">
          <div className="section-head"><span>WHAT'S DIFFERENT</span><h2>A match you can explain to a procurement committee</h2><p>Most matching tools return one percentage. That hides the decision.</p></div>
          <div className="cards-4">
            {[['2', 'Two axes, not one score', 'Fit says how well the business suits the scope. Readiness says whether the paperwork is in order. A high-fit, low-readiness SME is coachable, not rejected.'],
              ['R', 'Costed readiness plans', 'Each gap names the issuer, turnaround in days, cost in rand, and how many other open opportunities the same document unlocks.'],
              ['!', 'Capacity-risk flags', 'Overtrading, concentration and working-capital needs are flagged so a contract that could sink a small business is not celebrated as a win.'],
              ['+', 'Consortium assembly', 'When no single SME covers the scope, the platform bundles up to three SMEs over the line items and proposes a lead.']].map(([i, t, d]) => (
              <div className="value-card" key={t}><div className="icon">{i}</div><h3>{t}</h3><p>{d}</p></div>))}
          </div>
          <div style={{ maxWidth: 980, margin: '34px auto 0' }}>
            <div className="compare"><div className="table-wrap"><table>
              <thead><tr><th /><th>Typical matching tool</th><th>Kopano Match</th></tr></thead>
              <tbody>
                {[['Score', 'One blended percentage', 'Fit and readiness, plotted'],
                  ['Blocked SME', 'Filtered out', 'Kept, with a dated, costed plan'],
                  ['How it decides', 'Opaque or AI-scored', 'Deterministic rules; AI only explains'],
                  ['Risk to the SME', 'Not considered', 'Overtrading and cash-flow flags'],
                  ['Audit', 'Editable logs', 'Append-only, enforced by the database']].map(([a, b, c]) => (
                  <tr key={a}><td><b>{a}</b></td><td>{b}</td><td style={{ color: '#6d28d9', fontWeight: 600 }}>{c}</td></tr>))}
              </tbody></table></div></div>
          </div>
        </section>

        <section className="section" id="trust">
          <div className="section-head"><span>TRUST &amp; SECURITY</span><h2>Honest about what is built and what is not</h2><p>Each control is marked as in place or on the roadmap. Nothing here is claimed that the code does not do.</p></div>
          <div className="cards-4">
            {TRUST.map((c) => (
              <div className="value-card" key={c.t}><div className="icon">{c.i}</div><h3>{c.t}</h3><p>{c.d}</p>
                <div className="status"><Badge tone={c.ok ? 'green' : 'amber'}>{c.ok ? 'In place' : 'Roadmap'}</Badge></div></div>))}
          </div>
        </section>

        <section className="section white" id="users">
          <div className="section-head"><span>BUILT FOR THE ECOSYSTEM</span><h2>One platform, four role-specific workspaces</h2></div>
          <div className="cards-4">
            {ROLES.map((r) => (
              <div className="role-card" key={r.key}>
                <Badge tone="purple">{r.label}</Badge><h3>{r.label}</h3><p>{r.desc}</p>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: '#475467', lineHeight: 1.7 }}>{r.points.map((p) => <li key={p}>{p}</li>)}</ul>
                <button className="btn btn-outline btn-small" style={{ alignSelf: 'flex-start' }} onClick={() => open('signup', r.key)}>Join as {r.label}</button>
              </div>))}
          </div>
        </section>

        <section className="section navy" id="about">
          <div className="section-head"><span style={{ color: '#c5b7ff' }}>BUILT BY DIGI DIVA</span><h2>Practical digital infrastructure for SME growth</h2>
            <p>Kopano Match is developed by Digi Diva, combining product delivery, automation, data, security and SME-focused solution design. It is a working pilot: the specific list of what separates it from an enterprise deployment is published in the repository.</p></div>
        </section>
      </main>

      <footer className="site-footer">
        <span>© Digi Diva · Kopano Match pilot. Built against POPIA's conditions; not a claim of compliance.</span>
        <span><a href="/privacy">Privacy notice</a></span>
      </footer>

      {auth && <AuthModal mode={auth} role={role} setMode={setAuth} setRole={setRole} onClose={() => { setAuth(null); if (window.location.pathname !== '/') nav('/') }} />}
    </>
  )
}

function Ring({ v, label, color }: { v: number; label: string; color: string }) {
  return (
    <div className="score-ring" style={{ ['--v' as string]: v, ['--c' as string]: color, width: 84, height: 84 }}>
      <b style={{ fontSize: 20 }}>{Math.round(v)}<small>{label}</small></b>
    </div>
  )
}

function AuthModal({ mode, role, setMode, setRole, onClose }: {
  mode: 'login' | 'signup'; role: Exclude<Role, 'admin'>
  setMode: (m: 'login' | 'signup') => void; setRole: (r: Exclude<Role, 'admin'>) => void; onClose: () => void
}) {
  const { signIn } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const [f, setF] = useState({ full_name: '', organisation_name: '', email: '', phone: '', password: '', registration_number: '' })
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  async function submit(e: FormEvent) {
    e.preventDefault(); setError(null); setBusy(true)
    try {
      const { access_token } = mode === 'login'
        ? await api.login(f.email, f.password)
        : await api.register({ ...f, role, consent, phone: f.phone || null, registration_number: f.registration_number || null })
      const m = await signIn(access_token)
      onClose()
      toast(mode === 'login' ? 'Welcome back.' : 'Account created.')
      nav(homeFor(m.role))
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

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
          <div className="auth-tabs">
            <button className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')}>Create account</button>
            <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Log in</button>
          </div>
          <form onSubmit={submit}>
            {mode === 'signup' ? <>
              <h3 className="form-title">Create your account</h3>
              <p className="form-sub">Choose your role first. Your workspace is tailored to it.</p>
              <div className="field"><span className="lbl">I am joining as</span>
                <div className="role-grid">{ROLES.map((r) => (
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
                <div className="field"><label htmlFor="p">Password</label><input id="p" type="password" required minLength={12} autoComplete="new-password" value={f.password} onChange={set('password')} placeholder="Minimum 12 characters" /></div>
              </div>
              <label className="check-row"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                <span>I have read the <a href="/privacy" target="_blank" rel="noreferrer" style={{ color: 'var(--purple)' }}>privacy notice</a> and consent to my information being processed as described.</span></label>
              <button className="btn btn-primary btn-full" disabled={!consent || busy}>{busy ? 'Creating…' : 'Create account'}</button>
              <p className="hint" style={{ marginTop: 12 }}>Platform reviewer accounts are invite-only.</p>
            </> : <>
              <h3 className="form-title">Welcome back</h3>
              <p className="form-sub">Log in to your Kopano Match workspace.</p>
              <ErrorNote error={error} />
              <div className="field"><label htmlFor="le">Email address</label><input id="le" type="email" required autoComplete="username" value={f.email} onChange={set('email')} /></div>
              <div className="field"><label htmlFor="lp">Password</label><input id="lp" type="password" required autoComplete="current-password" value={f.password} onChange={set('password')} /></div>
              <button className="btn btn-primary btn-full" disabled={busy}>{busy ? 'Signing in…' : 'Log in'}</button>
              <div className="callout blue"><b>Demo accounts</b> (password <code>Demo-Password-1!</code>). Click one to fill the email:
                <div className="chips">{DEMO.map(([l, e]) => <button type="button" key={e} className="chip" onClick={() => setF({ ...f, email: e, password: 'Demo-Password-1!' })}>{l}</button>)}</div></div>
            </>}
          </form>
        </div>
      </div>
    </Modal>
  )
}
