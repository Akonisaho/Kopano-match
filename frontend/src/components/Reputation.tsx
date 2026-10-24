import { useState } from 'react'
import { api, dateFmt, type Eligible, type Reputation, type ReputationReview, type ReviewContext } from '../api'
import { useLoad } from '../hooks'
import { Badge, Panel, Spinner, useToast } from '../ui'

export const KIND_LABEL: Record<string, string> = {
  procurement: 'Procurement / Contract Delivery', training: 'Training Programme', incubation: 'Incubation Programme',
  acceleration: 'Acceleration Programme', mentorship: 'Mentorship', funding: 'Funding Programme', grant: 'Grant Programme',
  supplier_dev: 'Supplier Development Programme', enterprise_dev: 'Enterprise Development Programme',
  business_support: 'Business Support Programme', investment: 'Investment Relationship', other: 'Other Verified Engagement',
}

/** Read-only stars. The value is rounded to the nearest whole star. */
export function Stars({ value, size = 18 }: { value: number; size?: number }) {
  const full = Math.round(value)
  return (
    <span className="rv-stars" style={{ fontSize: size }} role="img" aria-label={`${value} out of 5 stars`}>
      {[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= full ? 'on' : ''}>★</i>)}
    </span>
  )
}

/** The compact rating shown beside a business. A business with no reviews says so, never zero. */
export function StarChip({ rating, reviews }: { rating?: number | null; reviews?: number }) {
  if (!reviews || rating == null) return <span className="rv-none">No ratings yet</span>
  return <span className="rv-chip" title={`${reviews} verified review${reviews === 1 ? '' : 's'}`}><i>★</i> {rating.toFixed(1)} <small>({reviews})</small></span>
}

function chips(r: { context: ReputationReview['context']; kind: string }) {
  const c = r.context
  const out: string[] = []
  if (c.total_sessions != null && c.sessions_attended != null) {
    out.push(`Attendance: ${c.sessions_attended}/${c.total_sessions} sessions (${Math.round((c.sessions_attended / c.total_sessions) * 100)}%)`)
  }
  if (c.duration) out.push(`Duration: ${c.duration}`)
  if (c.completion) out.push(c.completion === 'completed' ? 'Completed' : c.completion === 'in_progress' ? 'In progress' : 'Not completed')
  return out
}

export function ReviewCard({ r }: { r: ReputationReview }) {
  const extra = chips(r)
  return (
    <article className="rv-card">
      <div className="rv-top">
        <Stars value={r.rating} /> <b className="rv-num">{r.rating.toFixed(0)}/5</b>
        <span className="hint">· {dateFmt(r.created_at)}</span>
        {r.status === 'disputed' && <Badge tone="amber">Under review</Badge>}
      </div>
      <div className="rv-who"><b>{r.reviewer}</b> <Badge tone="green">Verified organisation</Badge> <span className="hint">{r.reviewer_type}</span></div>
      {r.comment && <p className="rv-text">“{r.comment}”</p>}
      <div className="rv-meta">
        <span className="rv-kind">{r.programme ? `${r.programme} · ` : ''}{r.kind_label}</span>
        {extra.map((x) => <span key={x} className="rv-pill">{x}</span>)}
        <span className="rv-pill ok">✓ Verified review</span>
      </div>
      {r.response && <p className="quote reply"><b>Response from the business:</b> {r.response}</p>}
    </article>
  )
}

/**
 * One star rating and a count, then supporting context. The rating is context for a corporate: the
 * matching engine does not read it, and it never moves a match score.
 */
export function ReputationPanel({ r, mine, showReviews = true }: { r: Reputation; mine?: boolean; showReviews?: boolean }) {
  const none = r.reviews === 0
  const max = Math.max(1, ...Object.values(r.distribution))
  return (
    <>
      <Panel title="Ratings & reviews" sub="From verified organisations that have worked with this business"
        right={!none && <Badge tone={r.reliable ? 'green' : 'amber'}>{r.reliable ? 'Established' : 'Early signal'}</Badge>}>
        {none ? <div className="empty"><strong>No ratings yet</strong>
          {mine ? 'Verified organisations can rate you after a programme or an award. A new business is never scored zero.' : 'A new business is not scored zero. It simply has no reviews yet.'}</div>
          : <div className="rv-head">
            <div className="rv-big"><b>{r.rating?.toFixed(1)}</b><Stars value={r.rating ?? 0} size={22} />
              <span>{r.reviews} verified review{r.reviews === 1 ? '' : 's'}</span></div>
            <div className="rv-dist" aria-label="Reviews by star rating">
              {['5', '4', '3', '2', '1'].map((s) => (
                <div key={s}><span>{s}★</span><div className="progress" style={{ height: 7 }}><i style={{ width: `${(r.distribution[s] / max) * 100}%` }} /></div><em>{r.distribution[s]}</em></div>))}
            </div>
            <div className="rv-stats">
              <div><b>{r.stats.awards}</b><span>Opportunities awarded</span></div>
              <div><b>{r.stats.reviewed_contracts}</b><span>Contracts reviewed</span></div>
              <div><b>{r.stats.programmes}</b><span>Verified programmes</span></div>
            </div>
          </div>}
        {r.badges.length > 0 && <div className="rv-badges">{r.badges.map((b) => <span key={b.key} className="rv-badge" title={b.why}>✓ {b.label}</span>)}</div>}
        <p className="hint" style={{ margin: '12px 0 0' }}>Kopano Match does not rely on self-declared experience alone. Only organisations with a confirmed relationship can review, and a rating never changes a match score.</p>
      </Panel>
      {showReviews && r.reviews_list.length > 0 && (
        <Panel title="Reviews" sub="Newest first. Every review is tied to a confirmed award, application or sign-up.">
          {r.reviews_list.map((x) => <ReviewCard key={x.id} r={x} />)}
        </Panel>)}
      {r.timeline.length > 0 && (
        <Panel title="Verified history">
          <ol className="rv-timeline">
            {r.timeline.map((t, i) => (
              <li key={i}><span className="rv-year">{new Date(t.when).getFullYear()}</span>
                <div><b>{t.title}</b><small>{t.detail}</small>{t.rating != null && <Stars value={t.rating} size={14} />}</div></li>))}
          </ol>
        </Panel>)}
    </>
  )
}

/** A corporate reads the ratings of a business that chose to be visible. */
export function TrackRecordReviews({ smeId }: { smeId: string }) {
  const t = useLoad<Reputation>(() => api.reputation(smeId), [smeId])
  if (t.error) return null
  if (!t.data) return <Spinner />
  return <ReputationPanel r={t.data} />
}

const STAR_INPUT = [1, 2, 3, 4, 5]

/** A funder, support programme or corporate records a programme or engagement it ran with a business. */
export function EngagementPanel({ onDone }: { onDone?: () => void }) {
  const toast = useToast()
  const list = useLoad<Eligible[]>(() => api.eligible())
  const [sme, setSme] = useState('')
  const [kind, setKind] = useState('training')
  const [programme, setProgramme] = useState('')
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const [total, setTotal] = useState('')
  const [attended, setAttended] = useState('')
  const [duration, setDuration] = useState('')
  const [completion, setCompletion] = useState('')
  const [busy, setBusy] = useState(false)
  if (!list.data) return <Spinner />
  const ok = sme && programme.trim().length >= 3 && rating > 0
  async function submit() {
    setBusy(true)
    try {
      await api.leaveEngagement({
        sme_id: sme, kind, programme: programme.trim(), rating, comment: comment.trim() || undefined,
        context: {
          ...(duration && { duration }), ...(total && { total_sessions: +total }),
          ...(attended && { sessions_attended: +attended }),
          ...(completion && { completion: completion as ReviewContext['completion'] }),
        },
      })
      toast('Review recorded. The business can respond to it.')
      setProgramme(''); setRating(0); setComment(''); setTotal(''); setAttended(''); setDuration(''); setCompletion('')
      onDone?.()
    } catch (err) { toast((err as Error).message, 'error') } finally { setBusy(false) }
  }
  return (
    <Panel title="Review a programme or engagement" sub="Training, incubation, funding and support. You can review a business that applied to you or that you signed up.">
      {list.data.length === 0 ? <p className="hint" style={{ margin: 0 }}>No business has applied to your opportunities yet, so there is nobody to review.</p> : (
        <div className="rv-form">
          <label className="field">Business
            <select value={sme} onChange={(e) => setSme(e.target.value)}>
              <option value="">Choose a business</option>
              {list.data.map((o) => <option key={o.sme_id} value={o.sme_id}>{o.name} ({o.basis === 'assisted' ? 'you signed it up' : 'applied to you'})</option>)}
            </select></label>
          <label className="field">What are you reviewing?
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(KIND_LABEL).filter(([k]) => k !== 'procurement').map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select></label>
          <label className="field">Programme name
            <input value={programme} maxLength={200} onChange={(e) => setProgramme(e.target.value)} placeholder="e.g. Financial Management Training" /></label>
          <div className="rate-row"><span>Overall rating</span>
            <span className="stars" role="radiogroup" aria-label="Overall rating">
              {STAR_INPUT.map((n) => <button key={n} type="button" className={n <= rating ? 'on' : ''} onClick={() => setRating(n)} aria-label={`${n} star${n > 1 ? 's' : ''}`}>★</button>)}
            </span></div>
          <div className="rv-grid">
            <label className="field">Duration<input value={duration} maxLength={40} onChange={(e) => setDuration(e.target.value)} placeholder="5 days" /></label>
            <label className="field">Sessions in total<input type="number" min={1} value={total} onChange={(e) => setTotal(e.target.value)} /></label>
            <label className="field">Sessions attended<input type="number" min={0} value={attended} onChange={(e) => setAttended(e.target.value)} /></label>
            <label className="field">Status
              <select value={completion} onChange={(e) => setCompletion(e.target.value)}>
                <option value="">Not stated</option><option value="completed">Completed</option>
                <option value="in_progress">In progress</option><option value="not_completed">Not completed</option>
              </select></label>
          </div>
          <label className="field">Your review (optional)
            <textarea rows={3} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="What did the business do well?" /></label>
          <p className="hint">Attendance is a record of attending. It is not shown as a certificate. Leave out phone numbers, email addresses and ID numbers.</p>
          <button className="btn btn-primary" disabled={!ok || busy} onClick={submit}>{busy ? 'Saving…' : 'Record review'}</button>
        </div>)}
    </Panel>
  )
}
