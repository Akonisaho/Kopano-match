import { useEffect, useState } from 'react'
import { zar } from '../api'
import { useT } from '../i18n'

const HOLD = [1900, 1600, 1600, 2800, 3600]
const TARGET = 4_200_000
const REDUCED = typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const SPARKS = Array.from({ length: 16 }, (_, i) => ({ a: (i / 16) * 360 + (i % 2) * 11, d: 46 + (i % 4) * 14, t: 0.55 + (i % 5) * 0.09 }))

/** The whole pitch in ten seconds: blocked, two documents named, then the contract value unlocks. */
export default function UnlockStage() {
  const t = useT()
  const [s, setS] = useState(REDUCED ? 4 : 0)
  const [n, setN] = useState(REDUCED ? TARGET : 0)

  useEffect(() => {
    if (REDUCED) return
    const t = setTimeout(() => setS((x) => (x + 1) % HOLD.length), HOLD[s])
    return () => clearTimeout(t)
  }, [s])

  useEffect(() => {
    if (REDUCED) return
    if (s === 0) { setN(0); return }
    if (s !== 3) return
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / 1900)
      setN(Math.round(TARGET * (1 - Math.pow(1 - k, 3))))
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [s])

  const ready = s >= 3
  const x0 = 100, y0 = 205, x1 = 268, y1 = 78
  const x = ready ? x1 : x0
  const y = ready ? y1 : y0
  return (
    <div className="lx-stage" aria-label="A business is blocked by two documents, uploads them, and unlocks a R4.2 million contract">
      <div className="lx-stage-top">
        <span>{t('Sample supplier · Roads tender')}</span>
        <span className={`lx-pill ${ready ? 'on' : ''}`}>{ready ? t('Award ready') : t('Coachable')}</span>
      </div>
      <svg viewBox="0 0 360 290" className="lx-chart" aria-hidden>
        <defs>
          <radialGradient id="lxglow"><stop offset="0" stopColor="#ffd166" stopOpacity="1" /><stop offset="1" stopColor="#ffd166" stopOpacity="0" /></radialGradient>
          <linearGradient id="lxtrail" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stopColor="#f59e0b" stopOpacity="0" /><stop offset="1" stopColor="#ffd166" /></linearGradient>
          <linearGradient id="lxzone" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#a78bfa" stopOpacity=".5" /><stop offset="1" stopColor="#fb7185" stopOpacity=".32" /></linearGradient>
          <pattern id="lxgrid" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="rgba(255,255,255,.07)" /></pattern>
        </defs>
        <rect x="36" y="24" width="300" height="236" rx="18" fill="url(#lxgrid)" stroke="rgba(255,255,255,.16)" />
        <rect x="186" y="24" width="150" height="104" rx="16" fill="url(#lxzone)" className={`lx-zone ${ready ? 'on' : ''}`} />
        <line x1="186" y1="24" x2="186" y2="260" stroke="rgba(255,255,255,.3)" strokeDasharray="4 7" />
        <line x1="36" y1="128" x2="336" y2="128" stroke="rgba(255,255,255,.3)" strokeDasharray="4 7" />
        <text x="261" y="50" textAnchor="middle" fontSize="11" fontWeight="800" fill="#fff" letterSpacing="2.4" opacity={ready ? 1 : 0.55}>{t('AWARD READY')}</text>
        <text x="111" y="248" textAnchor="middle" fontSize="11" fontWeight="800" fill="rgba(255,255,255,.4)" letterSpacing="2.4">{t('NOT YET')}</text>
        <line x1={x0} y1={y0} x2={x1} y2={y1} stroke="url(#lxtrail)" strokeWidth="3" strokeLinecap="round" strokeDasharray="230" strokeDashoffset={ready ? 0 : 230} className="lx-trail" />
        <circle cx={x} cy={y} r={ready ? 46 : 26} fill="url(#lxglow)" opacity={ready ? 0.85 : 0.35} className="lx-dot" />
        <circle cx={x} cy={y} r="11" fill="#ffd166" stroke="#fff" strokeWidth="3" className="lx-dot" />
        {ready && s === 3 && SPARKS.map((p, i) => (
          <circle key={i} cx={x} cy={y} r="2.6" fill={i % 3 ? '#ffd166' : '#fda4af'} className="lx-spark"
            style={{ ['--dx' as string]: `${Math.cos((p.a * Math.PI) / 180) * p.d}px`, ['--dy' as string]: `${Math.sin((p.a * Math.PI) / 180) * p.d}px`, animationDuration: `${p.t}s` }} />))}
      </svg>
      <div className="lx-stage-foot">
        <div className="lx-count">
          <small>{ready ? t('Unlocked') : t('Waiting behind two documents')}</small>
          <b className={ready ? '' : 'dim'}>{zar(ready ? n : TARGET)}</b>
        </div>
        <ul className="lx-docs">
          <li className={s >= 1 ? 'in' : ''}><i className={s >= 2 ? 'ok' : ''}>{s >= 2 ? '✓' : ''}</i><div><b>{t('Tax PIN')}</b><small>{t('{n} days', { n: 7 })} · R0</small></div></li>
          <li className={s >= 2 ? 'in' : ''}><i className={s >= 3 ? 'ok' : ''}>{s >= 3 ? '✓' : ''}</i><div><b>{t('Good standing')}</b><small>{t('{n} days', { n: 14 })} · R0</small></div></li>
        </ul>
      </div>
    </div>
  )
}
