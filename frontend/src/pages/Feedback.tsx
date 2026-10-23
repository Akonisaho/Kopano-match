import { useState } from 'react'
import { api, dateFmt, zar, type FeedbackItem, type Performance } from '../api'
import { useLoad } from '../hooks'
import { Badge, Modal, Panel, Spinner, Welcome, useToast } from '../ui'

export const CRITERIA: [string, string][] = [
  ['quality', 'Quality of work'], ['delivery', 'Delivery on time'], ['responsiveness', 'Responsiveness'],
  ['compliance', 'Compliance'], ['innovation', 'Innovation'], ['value_for_money', 'Value for money'],
]
const STATUS_TONE: Record<string, string> = { published: 'blue', responded: 'green', disputed: 'amber', upheld: 'gray', removed: 'red' }
const STATUS_LABEL: Record<string, string> = {
  published: 'Published', responded: 'Answered', disputed: 'Disputed', upheld: 'Kept after review', removed: 'Removed after review',
}

function Rating({ value, onChange }: { value: number; onChange?: (n: number) => void }) {
  return (
    <span className="stars" role={onChange ? 'radiogroup' : 'img'} aria-label={`${value} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" className={n <= value ? 'on' : ''} disabled={!onChange}
          onClick={() => onChange?.(n)} aria-label={`${n} star${n > 1 ? 's' : ''}`}>★</button>))}
    </span>
  )
}

/** A business's track record. Fewer than three reviews is labelled an early signal, not a rating. */
export function PerformanceCard({ p, mine }: { p: Performance; mine?: boolean }) {
  if (!p.reviews) {
    return <Panel title="Track record"><p className="hint" style={{ margin: 0 }}>{mine ? 'No feedback yet. Buyers can rate your work once they have awarded it to you.' : 'No feedback on record yet.'}</p></Panel>
  }
  return (
    <Panel title="Track record" sub={`${p.reviews} review${p.reviews === 1 ? '' : 's'} from buyers that awarded this business work`}
      right={<Badge tone={p.reliable ? 'green' : 'amber'}>{p.reliable ? 'Established' : 'Early signal'}</Badge>}>
      <div className="perf-head"><b className="perf-score">{p.overall?.toFixed(1)}</b><span className="hint">out of 5 overall</span></div>
      {p.criteria.map((c) => (
        <div key={c.key} style={{ marginBottom: 9 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>{c.label}</span><b className="mono">{c.average ?? '–'}</b></div>
          <div className="progress" style={{ height: 7 }} aria-hidden><i style={{ width: `${((c.average ?? 0) / 5) * 100}%` }} /></div>
        </div>))}
      {p.summary && (
        <div className="callout purple" style={{ marginTop: 14, background: '#faf5ff', color: '#4c1d95', fontSize: 13 }}>
          <b>{p.summary.source === 'ai' ? 'AI summary of the ratings and comments' : 'Summary from the ratings'}</b>
          <p style={{ margin: '6px 0 0' }}>{p.summary.summary}</p>
          {p.summary.strengths.length > 0 && <p style={{ margin: '6px 0 0' }}><b>Strengths:</b> {p.summary.strengths.join(', ')}</p>}
          {p.summary.development_areas.length > 0 && <p style={{ margin: '4px 0 0' }}><b>To improve:</b> {p.summary.development_areas.join(', ')}</p>}
        </div>)}
      {!p.reliable && <p className="hint" style={{ marginBottom: 0 }}>Fewer than three reviews, so treat this as a first impression and not a verdict.</p>}
      {p.disputed_open > 0 && <p className="hint" style={{ marginBottom: 0 }}>{p.disputed_open} review{p.disputed_open > 1 ? 's are' : ' is'} being looked at by a reviewer.</p>}
    </Panel>
  )
}

function RatingForm({ appId, sme, onDone, onClose }: { appId: string; sme: string; onDone: () => void; onClose: () => void }) {
  const toast = useToast()
  const [r, setR] = useState<Record<string, number>>({})
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const complete = CRITERIA.every(([k]) => r[k])
  async function submit() {
    setBusy(true)
    try { await api.leaveFeedback(appId, r, comment); toast('Feedback sent. The business can respond to it.'); onDone(); onClose() }
    catch (err) { toast((err as Error).message, 'error') } finally { setBusy(false) }
  }
  return (
    <Modal small onClose={onClose}><div className="modal-pad">
      <h3 style={{ margin: '0 0 4px' }}>Rate {sme}</h3>
      <p className="hint" style={{ marginTop: 0 }}>Rate the work, not the person. The business sees this and can respond or dispute it.</p>
      {CRITERIA.map(([k, label]) => (
        <div key={k} className="rate-row"><span>{label}</span><Rating value={r[k] ?? 0} onChange={(n) => setR({ ...r, [k]: n })} /></div>))}
      <label className="field" style={{ marginTop: 12 }}>Comment (optional)
        <textarea rows={3} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="What went well, and what could improve?" />
      </label>
      <p className="hint">Leave out phone numbers, email addresses and ID numbers.</p>
      <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
        <button className="btn btn-outline" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={!complete || busy} onClick={submit}>{busy ? 'Sending…' : 'Send feedback'}</button>
      </div>
    </div></Modal>
  )
}

function FeedbackCard({ f, right, both }: { f: FeedbackItem; right?: React.ReactNode; both?: boolean }) {
  const avg = Object.values(f.ratings).reduce((a, b) => a + b, 0) / Math.max(1, Object.keys(f.ratings).length)
  return (
    <div className="feedback-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div><b>{both ? `${f.provider} on ${f.sme}` : right ? f.provider : f.sme}</b> <span className="hint">· {dateFmt(f.created_at)}</span></div>
        <Badge tone={STATUS_TONE[f.status]}>{STATUS_LABEL[f.status]}</Badge>
      </div>
      <div style={{ margin: '8px 0' }}><Rating value={Math.round(avg)} /> <span className="mono hint">{avg.toFixed(1)} average</span></div>
      <div className="criteria-line">{CRITERIA.map(([k, label]) => <span key={k}>{label} <b>{f.ratings[k]}</b></span>)}</div>
      {f.comment && <p className="quote">{f.comment}</p>}
      {f.response && <p className="quote reply"><b>Business response:</b> {f.response}</p>}
      {f.dispute_reason && <p className="quote reply"><b>Dispute:</b> {f.dispute_reason}</p>}
      {f.resolution_note && <p className="quote reply"><b>Reviewer:</b> {f.resolution_note}</p>}
      {right}
    </div>
  )
}

/** Buyer view: rate awarded work, and see what you have already said. */
export function ProviderFeedback() {
  const waiting = useLoad(() => api.feedbackAwaiting())
  const given = useLoad(() => api.feedbackGiven())
  const [open, setOpen] = useState<{ id: string; sme: string } | null>(null)
  if (!waiting.data || !given.data) return <Spinner />
  const reload = () => { waiting.reload(); given.reload() }
  return (
    <>
      <Welcome title="Feedback" text="After you award work, rate how it went. Ratings build a fair track record that other buyers can see. The business can respond, or dispute a rating for a reviewer to decide." />
      <Panel title="Awards waiting for your feedback">
        {waiting.data.length ? <div className="table-wrap"><table>
          <thead><tr><th>Business</th><th>Opportunity</th><th>Value</th><th>Awarded</th><th /></tr></thead>
          <tbody>{waiting.data.map((a) => (
            <tr key={a.application_id}><td><b>{a.sme}</b></td><td>{a.opportunity}</td><td>{zar(a.awarded_value)}</td><td>{dateFmt(a.awarded_at)}</td>
              <td><button className="btn btn-primary btn-small" onClick={() => setOpen({ id: a.application_id, sme: a.sme })}>Rate</button></td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>Nothing waiting</strong>Awards you have made appear here until you rate them.</div>}
      </Panel>
      <Panel title="Feedback you have given">
        {given.data.length ? given.data.map((f) => <FeedbackCard key={f.id} f={f} />) : <p className="hint" style={{ margin: 0 }}>No feedback given yet.</p>}
      </Panel>
      {open && <RatingForm appId={open.id} sme={open.sme} onDone={reload} onClose={() => setOpen(null)} />}
    </>
  )
}

function Answer({ f, onDone }: { f: FeedbackItem; onDone: () => void }) {
  const toast = useToast()
  const [mode, setMode] = useState<null | 'respond' | 'dispute'>(null)
  const [text, setText] = useState('')
  async function send() {
    try {
      await (mode === 'respond' ? api.respondFeedback(f.id, text) : api.disputeFeedback(f.id, text))
      toast(mode === 'respond' ? 'Your response is now shown with the feedback.' : 'Dispute sent. A reviewer will decide.')
      setMode(null); setText(''); onDone()
    } catch (err) { toast((err as Error).message, 'error') }
  }
  const canDispute = !['disputed', 'upheld', 'removed'].includes(f.status)
  return (
    <>
      {!mode && <div className="table-actions" style={{ marginTop: 10 }}>
        {!f.response && <button className="btn btn-outline btn-small" onClick={() => setMode('respond')}>Respond</button>}
        {canDispute && <button className="btn btn-outline btn-small" onClick={() => setMode('dispute')}>Dispute</button>}
      </div>}
      {mode && <div style={{ marginTop: 10 }}>
        <textarea rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)}
          placeholder={mode === 'respond' ? 'Add your side. It is shown next to the feedback.' : 'Why do you think this is unfair? A reviewer will read it.'} />
        <div className="table-actions" style={{ marginTop: 8 }}>
          <button className="btn btn-primary btn-small" disabled={text.trim().length < 3} onClick={send}>{mode === 'respond' ? 'Post response' : 'Send dispute'}</button>
          <button className="btn btn-outline btn-small" onClick={() => setMode(null)}>Cancel</button></div>
      </div>}
    </>
  )
}

/** Business view: your track record, and every review with the right to answer. */
export function SmeFeedback() {
  const d = useLoad(() => api.feedbackMine())
  if (!d.data) return <Spinner />
  return (
    <>
      <Welcome title="Feedback" text="What buyers have said about work you were awarded. You can add your side, or dispute a review you think is unfair. A reviewer decides disputes." />
      <div className="grid-2" style={{ gridTemplateColumns: '1fr 1.4fr' }}>
        <PerformanceCard p={d.data.performance} mine />
        <Panel title="Reviews">
          {d.data.items.length ? d.data.items.map((f) => <FeedbackCard key={f.id} f={f} right={<Answer f={f} onDone={d.reload} />} />)
            : <div className="empty"><strong>No reviews yet</strong>Once a buyer awards you work and rates it, it appears here.</div>}
        </Panel>
      </div>
    </>
  )
}

/** Reviewer view: disputed feedback waiting for a decision. */
export function DisputeQueue() {
  const toast = useToast()
  const q = useLoad(() => api.feedbackDisputes())
  const [note, setNote] = useState<Record<string, string>>({})
  async function decide(id: string, decision: 'uphold' | 'remove') {
    try { await api.resolveFeedback(id, decision, note[id] ?? ''); toast('Decision recorded in the audit log.'); q.reload() }
    catch (err) { toast((err as Error).message, 'error') }
  }
  if (!q.data) return <Spinner />
  return (
    <Panel title="Disputed feedback" sub="A business thinks a review is unfair. Read both sides, then keep it or remove it.">
      {q.data.length ? q.data.map((f) => (
        <div key={f.id}>
          <FeedbackCard f={f} both />
          <label className="field" style={{ margin: '8px 0 0' }}>Reason for your decision
            <input value={note[f.id] ?? ''} onChange={(e) => setNote({ ...note, [f.id]: e.target.value })} maxLength={500} /></label>
          <div className="table-actions" style={{ margin: '8px 0 18px' }}>
            <button className="btn btn-outline btn-small" disabled={(note[f.id] ?? '').trim().length < 3} onClick={() => decide(f.id, 'uphold')}>Keep the feedback</button>
            <button className="btn btn-primary btn-small" disabled={(note[f.id] ?? '').trim().length < 3} onClick={() => decide(f.id, 'remove')}>Remove it</button></div>
        </div>)) : <div className="empty"><strong>Nothing waiting</strong>Disputed feedback appears here.</div>}
    </Panel>
  )
}

