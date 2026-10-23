import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, zar } from '../api'
import { useToast } from '../ui'

export interface Unlocked { match_id: string; opportunity: string; contract_value: number }

const SPARKS = Array.from({ length: 28 }, (_, i) => ({ a: (i / 28) * 360, d: 120 + (i % 5) * 36, t: 0.9 + (i % 4) * 0.18, c: i % 3 }))

/** The moment the last document lands: the contract value unlocks, and one click applies. */
export default function UnlockCelebration({ items, onClose }: { items: Unlocked[]; onClose: () => void }) {
  const toast = useToast()
  const total = items.reduce((s, i) => s + i.contract_value, 0)
  const [n, setN] = useState(0)
  const [applied, setApplied] = useState<string[]>([])

  useEffect(() => {
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / 1500)
      setN(Math.round(total * (1 - Math.pow(1 - k, 3))))
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [total])

  async function apply(id: string) {
    try { await api.apply(id); setApplied((a) => [...a, id]); toast('Applied. The buyer has been told.') } catch (err) { toast((err as Error).message, 'error') }
  }
  return (
    <div className="celebrate" role="dialog" aria-modal="true" aria-label="Contract unlocked">
      <div className="celebrate-sparks" aria-hidden>
        {SPARKS.map((p, i) => (
          <i key={i} className={`c${p.c}`} style={{ ['--dx' as string]: `${Math.cos((p.a * Math.PI) / 180) * p.d}px`, ['--dy' as string]: `${Math.sin((p.a * Math.PI) / 180) * p.d}px`, animationDuration: `${p.t}s` }} />))}
      </div>
      <div className="celebrate-card">
        <small>Unlocked</small>
        <h2>{zar(n)}</h2>
        <p>You are now <b>award ready</b> for {items.length === 1 ? 'this opportunity' : `${items.length} opportunities`}. The buyer has been told.</p>
        <div className="celebrate-list">
          {items.map((i) => (
            <div key={i.match_id} className="celebrate-row">
              <div><b>{i.opportunity}</b><span>{zar(i.contract_value)}</span></div>
              {applied.includes(i.match_id)
                ? <em>Applied ✓</em>
                : <button className="btn btn-light btn-small" onClick={() => apply(i.match_id)}>Apply now</button>}
            </div>))}
        </div>
        <div className="table-actions" style={{ justifyContent: 'center', marginTop: 18 }}>
          <Link className="btn btn-ghost" style={{ color: '#fff' }} to="/app" onClick={onClose}>Share my passport</Link>
          <button className="btn btn-ghost" style={{ color: '#fff' }} onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  )
}
