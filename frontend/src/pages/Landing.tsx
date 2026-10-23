import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Evaluation, type Role } from '../api'
import { homeFor, useAuth } from '../auth'
import AuthModal from '../components/AuthModal'
import { Icon } from '../components/Icon'
import UnlockStage from '../components/UnlockStage'
import { Logo } from '../ui'

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

const BUSINESS = [['Verify once', 'Registry, tax and identity checks, each with its source shown.'], ['See the gap', 'Every missing document, with the days and rand to fix it.'], ['Share your passport', 'One link that proves what you can show any buyer.']]
const BUYER = [['Post as rules', 'Requirements become gates and weighted preferences.'], ['Get a ranked shortlist', 'Two scores each, with reasons, and a warning when a contract is too big.'], ['Award, then rate', 'Structured feedback builds a track record a business can answer.']]
const EDGE: [string, string, string][] = [
  ['layers', 'Two scores, not one', 'A strong business with missing paperwork is coachable, never just rejected.'],
  ['wallet', 'Gaps with a price tag', 'Issuer, days and rand for every missing document.'],
  ['users', 'We build the team', 'When nobody covers the scope alone, a consortium is assembled.'],
  ['id', 'A passport that travels', 'Proof the business owns and shares, on or off the platform.'],
]

/** Adds `in` to an element once it scrolls into view, so sections arrive instead of just sitting there. */
function Reveal({ children, className = '', delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [on, setOn] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') { setOn(true); return }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setOn(true); io.disconnect() } }, { threshold: 0.18 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return <div ref={ref} className={`lx-reveal ${on ? 'in' : ''} ${className}`} style={{ transitionDelay: `${delay}ms` }}>{children}</div>
}

export default function Landing({ initialAuth }: { initialAuth?: 'login' | 'signup' }) {
  const [auth, setAuth] = useState<'login' | 'signup' | null>(initialAuth ?? null)
  const [role, setRole] = useState<Exclude<Role, 'admin'>>('sme')
  const [ev, setEv] = useState<Evaluation | null>(null)
  const [solid, setSolid] = useState(false)
  const { me } = useAuth()
  const nav = useNavigate()
  const open = (mode: 'login' | 'signup', r?: Exclude<Role, 'admin'>) => { if (r) setRole(r); setAuth(mode) }

  useEffect(() => { api.evaluation().then(setEv).catch(() => setEv(null)) }, [])
  useEffect(() => {
    const on = () => setSolid(window.scrollY > 40)
    on(); window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])

  const flipped = ev?.fairness.scores_changed_by_ownership ?? 0
  const pairs = ev?.fairness.counterfactual_pairs

  return (
    <div className="lx">
      <header className={`lx-top ${solid ? 'solid' : ''}`}>
        <Logo dark />
        <nav className="lx-nav"><a href="#how">How it works</a><a href="#edge">Why it wins</a><Link to="/responsible-ai">Responsible AI</Link></nav>
        <div className="lx-actions">
          {me ? <button className="lx-btn lx-btn-gold" onClick={() => nav(homeFor(me.role))}>Open workspace</button> : <>
            <button className="lx-btn lx-btn-ghost" onClick={() => open('login')}>Log in</button>
            <button className="lx-btn lx-btn-gold" onClick={() => open('signup')}>Get started</button></>}
        </div>
      </header>

      <main>
        <section className="lx-hero">
          <div className="lx-aurora" aria-hidden><i /><i /><i /></div>
          <div className="lx-stars" aria-hidden />
          <div className="lx-hero-copy">
            <span className="lx-eyebrow">Verified SME opportunity platform</span>
            <h1>Stop losing contracts to <em>paperwork.</em></h1>
            <p>Every small business sees what stands between them and the deal: how long it takes, what it costs, and what it unlocks.</p>
            <div className="lx-cta">
              <button className="lx-btn lx-btn-gold lx-btn-lg" onClick={() => open('signup')}>Join Kopano Match <Icon name="arrow" size={18} /></button>
              <a className="lx-btn lx-btn-ghost lx-btn-lg" href="#how">See how it works</a>
            </div>
          </div>
          <div className="lx-hero-stage"><UnlockStage /></div>
          <a className="lx-scroll" href="#proof" aria-label="Scroll down"><span /></a>
        </section>

        <section className="lx-proof" id="proof">
          <Reveal className="lx-proof-item"><b>2</b><span>scores, not one.<br />Fit and readiness.</span></Reveal>
          <Reveal className="lx-proof-item" delay={120}><b>R4.2m</b><span>unlocked by two documents<br />in our demo.</span></Reveal>
          <Reveal className="lx-proof-item" delay={240}><b>{flipped}</b><span>of {pairs ?? '360'} scores changed when<br />we flipped ownership.</span></Reveal>
        </section>

        <section className="lx-section" id="how">
          <Reveal><h2>One journey, two sides.</h2></Reveal>
          <div className="lx-two">
            {[['For businesses', BUSINESS], ['For buyers and funders', BUYER]].map(([title, steps], side) => (
              <Reveal key={title as string} className="lx-panel" delay={side * 140}>
                <h3>{title as string}</h3>
                {(steps as string[][]).map(([t, d], i) => (
                  <div className="lx-step" key={t}><b>{i + 1}</b><div><h4>{t}</h4><p>{d}</p></div></div>))}
              </Reveal>))}
          </div>
        </section>

        <section className="lx-section lx-edge" id="edge">
          <Reveal><span className="lx-eyebrow">Why it wins</span><h2>Everyone else says no.<br /><em>We say how.</em></h2></Reveal>
          <div className="lx-cards">
            {EDGE.map(([icon, t, d], i) => (
              <Reveal key={t} className="lx-card" delay={i * 110}><span className="lx-card-icon"><Icon name={icon} size={26} /></span><h3>{t}</h3><p>{d}</p></Reveal>))}
          </div>
        </section>

        <section className="lx-trust">
          <Reveal className="lx-trust-row">
            <span>Rules, not a black box</span><span>Append-only audit log</span><span>AI drafts, people decide</span><span>Built against POPIA</span>
            <Link to="/responsible-ai">See how we test it <Icon name="arrow" size={15} /></Link>
          </Reveal>
        </section>

        <section className="lx-final">
          <div className="lx-aurora small" aria-hidden><i /><i /></div>
          <Reveal>
            <h2>Be the business that’s ready.</h2>
            <div className="lx-cta" style={{ justifyContent: 'center' }}>
              <button className="lx-btn lx-btn-gold lx-btn-lg" onClick={() => open('signup', 'sme')}>I run a business</button>
              <button className="lx-btn lx-btn-ghost lx-btn-lg" onClick={() => open('signup', 'corporate')}>I buy or fund</button>
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="lx-foot">
        <span>© Digi Diva · Kopano Match pilot. Built against POPIA’s conditions; not a claim of compliance.</span>
        <span><Link to="/privacy">Privacy notice</Link> · <Link to="/responsible-ai">Responsible AI</Link></span>
      </footer>

      {auth && <AuthModal mode={auth} role={role} roles={ROLES} setMode={setAuth} setRole={setRole} onClose={() => { setAuth(null); if (window.location.pathname !== '/') nav('/') }} />}
    </div>
  )
}
