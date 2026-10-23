import { useState } from 'react'

const SME = [
  ['Thabo bids for a R4.2m roads contract.', 'He fits the work well, but a score of 35 on readiness means the paperwork is not there.'],
  ['Kopano names the two documents in the way.', 'Tax compliance PIN: 7 days, R0. Letter of good standing: 14 days, R0. Costed and dated, not a vague rejection.'],
  ['He uploads them and moves across the line.', 'Same fit, readiness up to 78. Award ready, before he spends a rand on a tender he would have lost.'],
]
const BUYER = [
  ['Metro posts a roads tender as rules.', 'Every requirement is a gate or a weighted preference. No keywords, no guesswork.'],
  ['Businesses come back ranked, with reasons.', 'Two scores each, the gaps costed, and a capacity flag when a contract is too big for the business.'],
  ['Nobody covers the agri-hub alone, so we assemble a team.', 'A three-business consortium covers 100% of the scope. Partner names stay hidden until all three accept.'],
]
const BARS: [string, number, number][] = [['Business A', 91, 88], ['Business B', 84, 72], ['Business C', 79, 41]]

/** Two short stories that carry the whole pitch. The dot moves when the document is uploaded. */
export default function TwoStories() {
  const [tab, setTab] = useState<'sme' | 'buyer'>('sme')
  const [done, setDone] = useState(false)
  const fit = 82, ready = done ? 78 : 35
  const x = 40 + (fit / 100) * 280, y = 260 - (ready / 100) * 220
  const steps = tab === 'sme' ? SME : BUYER
  return (
    <section className="section" id="stories">
      <div className="section-head">
        <span className="eyebrow">See it in two stories</span>
        <h2>From “not yet” to “award ready”</h2>
      </div>
      <div className="story-tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'sme'} className={tab === 'sme' ? 'on' : ''} onClick={() => setTab('sme')}>I run a small business</button>
        <button role="tab" aria-selected={tab === 'buyer'} className={tab === 'buyer' ? 'on' : ''} onClick={() => setTab('buyer')}>I buy or fund</button>
      </div>
      <div className="story">
        <ol className="story-steps">{steps.map(([t, d], i) => <li key={t}><b>{i + 1}</b><div><h3>{t}</h3><p>{d}</p></div></li>)}</ol>
        <div className="story-visual">
          {tab === 'sme' ? <>
            <svg viewBox="0 0 360 300" role="img" aria-label="Fit against readiness chart with one business moving into the award-ready corner">
              <rect x="40" y="40" width="280" height="220" rx="14" fill="#f8f9fd" stroke="#e3e9f2" />
              <rect x="40" y="40" width="112" height="220" fill="#eef2ff" opacity=".5" /><rect x="152" y="40" width="168" height="88" fill="#ede9fe" />
              <line x1="152" y1="40" x2="152" y2="260" stroke="#98a2b3" strokeDasharray="5 5" /><line x1="40" y1="128" x2="320" y2="128" stroke="#98a2b3" strokeDasharray="5 5" />
              <text x="236" y="62" textAnchor="middle" fontSize="12" fontWeight="700" fill="#6d28d9">Award ready</text>
              <text x="236" y="248" textAnchor="middle" fontSize="12" fontWeight="700" fill="#b45309">Coachable</text>
              <text x="180" y="286" textAnchor="middle" fontSize="12" fill="#667085">Fit</text>
              <text x="14" y="154" fontSize="12" fill="#667085" transform="rotate(-90 14 154)">Readiness</text>
              <circle cx={x} cy={y} r="13" fill={done ? '#7c3aed' : '#f59e0b'} stroke="#fff" strokeWidth="3" className="story-dot" />
            </svg>
            <button className="btn btn-primary" onClick={() => setDone(!done)}>{done ? 'Start again' : 'Upload the two documents'}</button>
          </> : <div className="story-bars">
            {BARS.map(([n, f, r]) => (
              <div key={n} className="story-row"><b>{n}</b>
                <div><span>Fit {f}</span><i style={{ width: `${f}%` }} /></div>
                <div><span>Ready {r}</span><i className="b" style={{ width: `${r}%` }} /></div></div>))}
            <p className="hint" style={{ marginBottom: 0 }}>Illustrative figures. The live demo uses real data.</p>
          </div>}
        </div>
      </div>
    </section>
  )
}
