import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Evaluation, type PublicCard, type Role } from '../api'
import AuthModal from '../components/AuthModal'
import { Icon } from '../components/Icon'
import LxTop from '../components/LxTop'
import UnlockStage from '../components/UnlockStage'
import { useT } from '../i18n'
import { ROLES } from '../roles'
import { OppCard } from './PublicOpps'

const BUSINESS = [['Verify once', 'Registry, tax and identity checks, each with its source shown.'], ['See the gap', 'Every missing document, with the days and rand to fix it.'], ['Share your passport', 'One link that proves what you can show any corporate.']]
const BUYER = [['Post as rules', 'Requirements become gates and weighted preferences.'], ['Get a ranked shortlist', 'Two scores each, with reasons, and a warning when a contract is too big.'], ['Award, then rate', 'Structured feedback builds a track record a business can answer.']]
const EDGE: [string, string, string][] = [
  ['layers', 'Two scores, not one', 'A strong business with missing paperwork is coachable, never just rejected.'],
  ['wallet', 'Gaps with a price tag', 'Issuer, days and rand for every missing document.'],
  ['users', 'We build the team', 'When nobody covers the scope alone, a consortium is assembled.'],
  ['id', 'A passport that travels', 'Proof the business owns and shares, on or off the platform.'],
]
const INCLUSIVE: [string, string][] = [
  ['Your language', 'English, Afrikaans, isiZulu and Sesotho. Your scores are the same in every language.'],
  ['Your voice', 'Listen to your next step, or speak to search instead of typing.'],
  ['With help', 'A support programme can set you up. You still choose your own password.'],
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
  const t = useT()
  const [auth, setAuth] = useState<'login' | 'signup' | null>(initialAuth ?? null)
  const [role, setRole] = useState<Exclude<Role, 'admin'>>('sme')
  const [ev, setEv] = useState<Evaluation | null>(null)
  const [opps, setOpps] = useState<PublicCard[]>([])
  const nav = useNavigate()
  const open = (mode: 'login' | 'signup', r?: Exclude<Role, 'admin'>) => { if (r) setRole(r); setAuth(mode) }

  useEffect(() => { api.evaluation().then(setEv).catch(() => setEv(null)) }, [])
  useEffect(() => { api.publicOpportunities().then(setOpps).catch(() => setOpps([])) }, [])

  const flipped = ev?.fairness.scores_changed_by_ownership ?? 0
  const pairs = ev?.fairness.counterfactual_pairs

  return (
    <div className="lx">
      <LxTop onLogin={() => open('login')} onSignup={() => open('signup')} />

      <main>
        <section className="lx-hero">
          <div className="lx-aurora" aria-hidden><i /><i /><i /></div>
          <div className="lx-stars" aria-hidden />
          <div className="lx-hero-copy">
            <span className="lx-eyebrow">{t('Verified SME opportunity platform')}</span>
            <h1>{t('Stop losing contracts to')} <em>{t('paperwork.')}</em></h1>
            <p>{t('Every small business sees what stands between them and the deal: how long it takes, what it costs, and what it unlocks.')}</p>
            <div className="lx-cta">
              <Link className="lx-btn lx-btn-gold lx-btn-lg" to="/opportunities">{t('Browse open opportunities')} <Icon name="arrow" size={18} /></Link>
              <button className="lx-btn lx-btn-ghost lx-btn-lg" onClick={() => open('signup')}>{t('Join free')}</button>
            </div>
          </div>
          <div className="lx-hero-stage"><UnlockStage /></div>
          <a className="lx-scroll" href="#proof" aria-label={t('Scroll down')}><span /></a>
        </section>

        <section className="lx-proof" id="proof">
          <Reveal className="lx-proof-item"><b>2</b><span>{t('scores, not one.')}<br />{t('Fit and readiness.')}</span></Reveal>
          <Reveal className="lx-proof-item" delay={120}><b>R4.2m</b><span>{t('unlocked by two documents')}<br />{t('in our demo.')}</span></Reveal>
          <Reveal className="lx-proof-item" delay={240}><b>{flipped}</b><span>{t('of {n} scores changed when', { n: pairs ?? '360' })}<br />{t('we flipped ownership.')}</span></Reveal>
        </section>

        {opps.length > 0 && (
          <section className="lx-section" id="live">
            <Reveal><span className="lx-eyebrow">{t('Live now · no sign-up needed')}</span><h2>{t('Open opportunities.')}<br /><em>{t('Check your fit in seconds.')}</em></h2></Reveal>
            <div className="lx-grid">{opps.slice(0, 3).map((o, i) => <Reveal key={o.id} delay={i * 110}><OppCard o={o} /></Reveal>)}</div>
            <Reveal><Link className="lx-btn lx-btn-ghost" to="/opportunities" style={{ marginTop: 26 }}>{t('Browse all {n}', { n: opps.length })} <Icon name="arrow" size={16} /></Link></Reveal>
          </section>)}

        <section className="lx-section" id="how">
          <Reveal><h2>{t('One journey, two sides.')}</h2></Reveal>
          <div className="lx-two">
            {[['For businesses', BUSINESS], ['For corporates and funders', BUYER]].map(([title, steps], side) => (
              <Reveal key={title as string} className="lx-panel" delay={side * 140}>
                <h3>{t(title as string)}</h3>
                {(steps as string[][]).map(([h, d], i) => (
                  <div className="lx-step" key={h}><b>{i + 1}</b><div><h4>{t(h)}</h4><p>{t(d)}</p></div></div>))}
              </Reveal>))}
          </div>
        </section>

        <section className="lx-section lx-edge" id="edge">
          <Reveal><span className="lx-eyebrow">{t('Why it wins')}</span><h2>{t('Everyone else says no.')}<br /><em>{t('We say how.')}</em></h2></Reveal>
          <div className="lx-cards">
            {EDGE.map(([icon, h, d], i) => (
              <Reveal key={h} className="lx-card" delay={i * 110}><span className="lx-card-icon"><Icon name={icon} size={26} /></span><h3>{t(h)}</h3><p>{t(d)}</p></Reveal>))}
          </div>
        </section>

        <section className="lx-section" id="inclusive">
          <Reveal><span className="lx-eyebrow">{t('Built for everyone')}</span><h2>{t('Your language should never')}<br /><em>{t('decide who wins.')}</em></h2></Reveal>
          <div className="lx-cards three">
            {INCLUSIVE.map(([h, d], i) => (
              <Reveal key={h} className="lx-card" delay={i * 110}><h3>{t(h)}</h3><p>{t(d)}</p></Reveal>))}
          </div>
        </section>

        <section className="lx-trust">
          <Reveal className="lx-trust-row">
            <span>{t('Rules, not a black box')}</span><span>{t('Append-only audit log')}</span><span>{t('AI drafts, people decide')}</span><span>{t('Built against POPIA')}</span>
            <Link to="/responsible-ai">{t('See how we test it')} <Icon name="arrow" size={15} /></Link>
          </Reveal>
        </section>

        <section className="lx-final">
          <div className="lx-aurora small" aria-hidden><i /><i /></div>
          <Reveal>
            <h2>{t('Be the business that’s ready.')}</h2>
            <div className="lx-cta" style={{ justifyContent: 'center' }}>
              <button className="lx-btn lx-btn-gold lx-btn-lg" onClick={() => open('signup', 'sme')}>{t('I run a business')}</button>
              <button className="lx-btn lx-btn-ghost lx-btn-lg" onClick={() => open('signup', 'corporate')}>{t('I buy or fund')}</button>
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="lx-foot">
        <span>{t('© Digi Diva · Kopano Match pilot. Built against POPIA’s conditions; not a claim of compliance.')}</span>
        <span><Link to="/privacy">{t('Privacy notice')}</Link> · <Link to="/responsible-ai">{t('Responsible AI')}</Link></span>
      </footer>

      {auth && <AuthModal mode={auth} role={role} roles={ROLES} setMode={setAuth} setRole={setRole} onClose={() => { setAuth(null); if (window.location.pathname !== '/') nav('/') }} />}
    </div>
  )
}
