import { MeaningCheck, TrackRecord } from '../components/AiPanels'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, dateFmt, isProvider, pretty, QUADRANT_COLOR, zar } from '../api'
import { useAuth } from '../auth'
import TwoStep from '../components/TwoStep'
import { useLoad } from '../hooks'
import { TRUST } from '../trust'
import {
  Badge, ErrorNote, Explainer, GapCard, Metric, Panel, QuadrantBadge, RiskPanel, ScoreBreakdown, ScoreRing, Spinner,
  VerificationRow, Welcome, useToast,
} from '../ui'

export function MatchDetail() {
  const { id = '' } = useParams()
  const { me } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const m = useLoad(() => api.match(id), [id])
  const apps = useLoad(() => (me?.role === 'sme' ? api.applications() : Promise.resolve([])), [me?.role])
  if (m.error) return <ErrorNote error={m.error} />
  if (!m.data || !apps.data || !me) return <Spinner />
  const d = m.data
  const procurement = d.opportunity.kind === 'procurement'
  const mandatory = d.gaps.filter((g) => g.mandatory)
  const days = Math.max(0, ...mandatory.map((g) => g.days))
  const cost = mandatory.reduce((s, g) => s + g.cost_zar, 0)
  const applied = apps.data.some((a) => a.match_id === d.match_id)
  const own = me.role === 'sme'

  async function act(kind: 'apply' | 'shortlist' | 'reject') {
    try {
      if (kind === 'apply') await api.apply(d.match_id); else await api.decide(d.match_id, kind)
      toast(kind === 'apply' ? 'Application submitted.' : kind === 'shortlist' ? 'Shortlisted.' : 'Rejected.')
      m.reload(); apps.reload()
    } catch (err) { toast((err as Error).message, 'error') }
  }

  return (
    <>
      <p className="hint" style={{ margin: '0 0 6px' }}>{d.opportunity.title} · {zar(d.opportunity.contract_value)}</p>
      <Welcome title={d.sme.name} text={`Model ${d.model_version} · ${d.gate === 'pass' ? 'All mandatory requirements met' : 'Mandatory documents outstanding'}`}
        action={<div className="table-actions">
          <button className="btn btn-outline" onClick={() => nav(-1)}>Back</button>
          <button className="btn btn-outline" onClick={() => nav(`/app/matches/${d.match_id}/dossier`)}>Decision dossier</button>
          {own && !applied && d.status !== 'rejected' && <button className="btn btn-primary" onClick={() => act('apply')}>Apply</button>}
          {own && applied && <Badge tone="blue">Applied</Badge>}
          {isProvider(me.role) && d.status === 'matched' && <>
            <button className="btn btn-primary" onClick={() => act('shortlist')}>Shortlist</button>
            <button className="btn btn-outline" onClick={() => act('reject')}>Reject</button></>}
          {d.status !== 'matched' && <Badge tone={d.status === 'shortlisted' ? 'green' : 'gray'}>{pretty(d.status)}</Badge>}
        </div>} />
      <Explainer />
      {mandatory.length > 0 && (
        <div className="callout amber" style={{ marginTop: 0, marginBottom: 18, fontSize: 14 }}>
          <b>{days} days and {zar(cost)}</b> stand between {own ? 'you' : 'this business'} and this opportunity.</div>)}
      <div className="grid-2">
        <Panel title="Two scores, not one" sub="Fit is how well the business suits the scope. Readiness is whether the paperwork is in order." right={<QuadrantBadge q={d.quadrant} />}>
          <div className="score-pair" style={{ marginBottom: 20 }}>
            <ScoreRing value={d.fit} label="Fit" /><ScoreRing value={d.readiness} label="Ready" color={QUADRANT_COLOR.coachable} />
            <p className="hint" style={{ margin: 0, maxWidth: 220 }}>Award-ready needs 60 or more on both. These numbers come from fixed rules, not an AI model.</p>
          </div>
          <h4 style={{ fontSize: 13, margin: '0 0 6px' }}>How fit was calculated</h4>
          <ScoreBreakdown components={d.components} />
        </Panel>
        <div>
          {procurement ? <RiskPanel r={d.risk_flags} contractValue={d.opportunity.contract_value} />
            : <Panel title="Capacity risk"><p className="hint" style={{ margin: 0 }}>Capacity flags apply to procurement contracts only, so none are shown for this opportunity type.</p></Panel>}
          <Panel title="Verification" sub="Each check shows its source.">{d.verifications.length ? d.verifications.map((v) => <VerificationRow key={v.id} v={v} />) : <p className="hint">No checks on record.</p>}</Panel>
        </div>
      </div>
      <div className="grid-2">
        <MeaningCheck matchId={d.match_id} />
        {!own && <TrackRecord smeId={d.sme.id} />}
      </div>
      <Panel title="Readiness gaps" sub="Each one is dated and costed, with how many other opportunities the same credential unlocks.">
        {d.gaps.length ? <div className="grid-gaps">{d.gaps.map((g) => <GapCard key={g.credential} g={g} />)}</div> : <p className="hint" style={{ margin: 0 }}>No open gaps.</p>}
      </Panel>
      <Panel title="Summary" right={<Badge tone="gray">{d.rationale_source === 'llm' ? 'AI-written from the figures' : 'Generated from the score breakdown'}</Badge>}>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.75 }}>{d.rationale}</p>
        <div className="callout blue">The summary explains the score; it does not set it. A person makes the final decision.</div>
      </Panel>
    </>
  )
}

export function SecurityCentre() {
  const { me, signOut } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const audit = useLoad(() => api.myAudit())
  const [confirm, setConfirm] = useState(false)
  if (!me) return null

  async function download() {
    try {
      const url = URL.createObjectURL(new Blob([JSON.stringify(await api.myData(), null, 2)], { type: 'application/json' }))
      const a = document.createElement('a'); a.href = url; a.download = 'my-kopano-data.json'; a.click(); URL.revokeObjectURL(url)
      toast('Your data has been downloaded.'); audit.reload()
    } catch (err) { toast((err as Error).message, 'error') }
  }
  async function erase() {
    try { await api.deleteMe(); signOut(); nav('/'); toast('Your account has been anonymised.') } catch (err) { toast((err as Error).message, 'error') }
  }
  const built = TRUST.filter((c) => c.ok).length
  return (
    <>
      <Welcome title="Trust and security centre" text="What protects this platform, marked honestly as in place or on the roadmap, plus your own activity and data rights."
        action={<Badge tone="green">{built} of {TRUST.length} controls in place</Badge>} />
      <div className="security-grid" style={{ marginBottom: 18 }}>
        {TRUST.map((c) => (
          <div className="security-card" key={c.t}><Badge tone={c.ok ? 'green' : 'amber'}>{c.ok ? 'In place' : 'Roadmap'}</Badge><h4>{c.t}</h4><p>{c.d}</p></div>))}
      </div>
      <div className="grid-2">
        <TwoStep />
        <Panel title="Your recent activity" sub="Recorded in a log the application cannot edit or delete." right={<Badge tone="blue">Traceable</Badge>}>
          {audit.data?.length ? <div className="table-wrap"><table>
            <thead><tr><th>When</th><th>Action</th><th>Record</th></tr></thead>
            <tbody>{audit.data.map((a, i) => <tr key={i}><td>{dateFmt(a.timestamp)} {new Date(a.timestamp).toLocaleTimeString('en-ZA', { hour: '2-digit', minute: '2-digit' })}</td><td>{pretty(a.action)}</td><td>{pretty(a.entity_type)}</td></tr>)}</tbody>
          </table></div> : <div className="empty">No activity recorded.</div>}
        </Panel>
        <Panel title="Your data (POPIA)" sub="Data subject participation.">
          <div className="metric-grid" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: 12 }}>
            <Metric label="Signed in as" value={<span style={{ fontSize: 14 }}>{me.email}</span>} /><Metric label="Role" value={<span style={{ fontSize: 16 }}>{pretty(me.role)}</span>} />
          </div>
          <p style={{ fontSize: 13, color: '#475467', lineHeight: 1.6 }}>Download everything held about you as a file, or remove your personal details. Deleting anonymises your name, email and phone. The log of actions stays, without your identity.</p>
          <div className="table-actions"><button className="btn btn-outline" onClick={download}>Download my data</button>
            {!confirm ? <button className="btn btn-danger" onClick={() => setConfirm(true)}>Delete my account</button>
              : <><button className="btn btn-danger" onClick={erase}>Yes, anonymise my account</button><button className="btn btn-outline" onClick={() => setConfirm(false)}>Cancel</button></>}</div>
          {confirm && <div className="callout red">This cannot be undone and you will be signed out.</div>}
        </Panel>
      </div>
    </>
  )
}
