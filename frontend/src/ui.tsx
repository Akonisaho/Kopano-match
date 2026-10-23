import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Gap, Quadrant, RiskFlags, Verification } from './api'
import { QUADRANT_BADGE, QUADRANT_LABEL, pretty, zar } from './api'
import { Icon, iconFor } from './components/Icon'

/* ---------- toasts ---------- */
interface Toast { id: number; text: string; kind: 'success' | 'error' | 'info' }
const ToastCtx = createContext<(text: string, kind?: Toast['kind']) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((text: string, kind: Toast['kind'] = 'success') => {
    const id = Date.now() + Math.random()
    setItems((x) => [...x, { id, text, kind }])
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 3200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-root" role="status" aria-live="polite">
        {items.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  )
}

/* ---------- modal ---------- */
export function Modal({ children, onClose, small }: { children: ReactNode; onClose: () => void; small?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${small ? 'small' : ''}`} role="dialog" aria-modal="true">
        <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        {children}
      </div>
    </div>
  )
}

/* ---------- small pieces ---------- */
export const Logo = ({ dark }: { dark?: boolean }) => (
  <span className="logo">
    {dark ? <img src="/favicon.png" alt="" style={{ height: 40 }} /> : <img src="/img/logo.png" alt="Kopano Match" style={{ height: 52 }} />}
    {dark && <span className="logo-copy light"><strong>Kopano Match</strong><span>by Digi Diva</span></span>}
  </span>
)

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export const QuadrantBadge = ({ q }: { q: Quadrant }) => <Badge tone={QUADRANT_BADGE[q]}>{QUADRANT_LABEL[q]}</Badge>

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="skeleton-wrap" role="status" aria-label={label}>
      <div className="skeleton sk-title" />
      <div className="skeleton-grid"><div className="skeleton sk-card" /><div className="skeleton sk-card" /><div className="skeleton sk-card" /><div className="skeleton sk-card" /></div>
      <div className="skeleton sk-panel" />
    </div>
  )
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? <div className="callout red" role="alert" style={{ marginTop: 0, marginBottom: 14 }}>{error}</div> : null
}

export function Metric({ label, value, note, tone }: { label: string; value: ReactNode; note?: string; tone?: string }) {
  return (
    <div className="metric">
      <div className="metric-top"><span>{label}</span><i className="metric-icon"><Icon name={iconFor(label)} size={16} /></i></div>
      <b style={tone ? { color: tone } : undefined}>{value}</b>{note && <small>{note}</small>}
    </div>
  )
}

export function Panel({ title, sub, right, children }: { title?: ReactNode; sub?: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      {(title || right) && <div className="panel-head"><div>{title && <h3>{title}</h3>}{sub && <p>{sub}</p>}</div>{right}</div>}
      {children}
    </section>
  )
}

export function Welcome({ eyebrow, title, text, action, hero }: { eyebrow?: string; title: string; text?: string; action?: ReactNode; hero?: boolean }) {
  return (
    <div className={`welcome${hero ? ' welcome-hero' : ''}`}>
      <div>{eyebrow && <span className="eyebrow dark">{eyebrow}</span>}<h1>{title}</h1>{text && <p>{text}</p>}</div>
      {action}
    </div>
  )
}

export function ScoreRing({ value, label, color = 'var(--purple)' }: { value: number; label?: string; color?: string }) {
  return (
    <div className="score-ring" style={{ ['--v' as string]: value, ['--c' as string]: color }} role="meter"
         aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label={label ?? 'Score'}>
      <b>{Math.round(value)}{label && <small>{label}</small>}</b>
    </div>
  )
}

/** Thin bar with the 60-point line marked, so the threshold is visible in every table. */
export function MiniBar({ value }: { value: number }) {
  return <div className="progress thin" aria-hidden><i style={{ width: `${value}%` }} /><span className="mark" /></div>
}

/** Always shows where the check came from, so a mock never reads as a real registry. */
export function VerificationRow({ v }: { v: Verification }) {
  const approved = v.review_status === 'approved'
  const ok = v.result === 'verified' || approved
  const rejected = v.review_status === 'rejected'
  const label = v.subject_type === 'document' ? `Document check${v.document_type ? ` · ${v.document_type}` : ''}`
    : ({ organisation: 'Company registration', identity: 'Representative identity' } as Record<string, string>)[v.subject_type] ?? pretty(v.subject_type)
  return (
    <div className="verify-row">
      <span className={`check-circle ${ok ? '' : rejected ? 'bad' : 'warn'}`}>{ok ? '✓' : '!'}</span>
      <div>
        <b>{label}{v.provider === 'tax' ? ' · tax status' : v.provider === 'registry' ? ' · registry' : ''}: {pretty(v.result)}</b>
        <small>Verification source: {v.source_label}{v.review_status ? ` · reviewer ${v.review_status}` : ''}</small>
      </div>
      <Badge tone={ok ? 'green' : rejected ? 'red' : 'amber'}>{ok ? 'Verified' : rejected ? 'Rejected' : 'In review'}</Badge>
    </div>
  )
}

export function GapCard({ g, blocks }: { g: Gap; blocks?: string[] }) {
  return (
    <div className="gap-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <h4>{g.label}</h4>
          <p>{g.status === 'expired' ? 'Expired: renew' : 'Missing: obtain'} from {g.issuer}</p>
        </div>
        <Badge tone={g.mandatory ? 'amber' : 'gray'}>{g.mandatory ? 'Mandatory' : 'Preferred'}</Badge>
      </div>
      <dl className="gap-facts">
        <div><dt>Turnaround</dt><dd>{g.days} days</dd></div>
        <div><dt>Cost</dt><dd>{zar(g.cost_zar)}</dd></div>
        <div><dt>Also unlocks</dt><dd>{g.also_unlocks} other {g.also_unlocks === 1 ? 'opportunity' : 'opportunities'}</dd></div>
      </dl>
      {blocks && blocks.length > 0 && <p className="hint" style={{ marginTop: 10 }}>Currently blocks: {blocks.join(', ')}</p>}
    </div>
  )
}

export function RiskPanel({ r, contractValue }: { r: RiskFlags; contractValue?: number }) {
  const rows = [
    { on: r.overtrading, title: 'Overtrading', text: `The contract is ${r.overtrading_pct}% of annual turnover (flagged above 250%).` },
    { on: r.concentration, title: 'Concentration', text: `One year of this contract is ${r.concentration_pct}% of annual turnover (flagged above 60%). Losing it later would be existential.` },
  ]
  return (
    <Panel title="Capacity risk" sub="Flags never reduce the fit score. They are shown so a bad match is not celebrated.">
      {rows.map((x) => (
        <div key={x.title} className="verify-row">
          <span className={`check-circle ${x.on ? 'bad' : ''}`}>{x.on ? '!' : '✓'}</span>
          <div><b>{x.title}</b><small>{x.on ? x.text : 'Not flagged.'}</small></div>
          <Badge tone={x.on ? 'red' : 'green'}>{x.on ? 'Flagged' : 'Clear'}</Badge>
        </div>
      ))}
      <div className="verify-row">
        <span className="check-circle idle">R</span>
        <div><b>Working capital before first payment</b><small>{contractValue ? `On a ${zar(contractValue)} contract` : 'Based on payment terms'}</small></div>
        <b className="mono">{zar(r.working_capital_zar)}</b>
      </div>
    </Panel>
  )
}

export function ScoreBreakdown({ components }: { components: Record<string, number> }) {
  const max: Record<string, number> = { capability: 40, capacity: 20, geography: 15, experience: 15, transformation: 10 }
  return (
    <table className="breakdown">
      <tbody>
        {Object.entries(components).map(([k, v]) => (
          <tr key={k}><td>{k === 'preferred_requirements' ? 'Unmet preferred rows' : pretty(k)}</td><td className="mono" style={{ textAlign: 'right' }}>{v.toFixed(1)}{max[k] ? ` / ${max[k]}` : ''}</td></tr>
        ))}
      </tbody>
    </table>
  )
}

/** Plain-language key to the two scores, shown where people first meet them. */
export function Explainer({ open }: { open?: boolean }) {
  return (
    <details className="explainer" open={open}>
      <summary>New here? How to read Fit and Readiness</summary>
      <dl>
        <dt>Fit</dt><dd>How well the business suits what is being asked for: capability, capacity to carry the contract, location and experience.</dd>
        <dt>Readiness</dt><dd>Whether the paperwork is in order: valid compliance documents and certificates. Expired ones count for 40%.</dd>
        <dt>Award ready</dt><dd>60 or more on both. A person still makes the final decision.</dd>
        <dt>Coachable</dt><dd>Good fit but missing paperwork. Each gap shows who issues it, how many days it takes and what it costs.</dd>
      </dl>
    </details>
  )
}

export function useGo() {
  const nav = useNavigate()
  return (to: string) => () => nav(to)
}
