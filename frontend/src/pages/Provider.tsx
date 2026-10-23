import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  api, dateFmt, daysUntil, KIND_LABEL, pretty, QUADRANT_COLOR, QUADRANT_LABEL, zar,
  type Kind, type Quadrant, type Role,
} from '../api'
import { useAuth } from '../auth'
import { useLoad } from '../hooks'
import QuadrantChart, { QuadrantLegend } from '../components/QuadrantChart'
import { Badge, ErrorNote, Explainer, Metric, MiniBar, Panel, QuadrantBadge, Spinner, Welcome, useToast } from '../ui'

const QUADS: Quadrant[] = ['award_now', 'coachable', 'ready_weak_fit', 'develop']
const KINDS_BY_ROLE: Record<string, Kind[]> = {
  corporate: ['procurement'], funder: ['grant', 'funding', 'investor'], support: ['support'],
}
const VALUE_LABEL: Record<Kind, string> = {
  procurement: 'Contract value (R)', grant: 'Grant pool (R)', funding: 'Funding amount (R)',
  investor: 'Investment amount (R)', support: 'Programme value (R)',
}
const FOCUS: Record<string, string> = { corporate: 'Supplier sourcing', funder: 'Funding and investment', support: 'Business support' }

/* ------------------------------------------------------------------ overview */

export function ProviderOverview() {
  const { me } = useAuth()
  const ov = useLoad(() => api.overview())
  const opps = useLoad(() => api.opportunities())
  if (!me || !ov.data || !opps.data) return <Spinner />
  const o = ov.data
  const verified = o.organisation?.verification_status === 'verified'
  const total = Object.values(o.by_quadrant).reduce((a, b) => a + (b ?? 0), 0)
  return (
    <>
      <Welcome eyebrow={FOCUS[me.role]} title={`${me.organisation?.name ?? 'Your organisation'} workspace`}
        text="Publish opportunities as rules, then review ranked, explainable SME matches. The system ranks; you decide."
        action={<Link className="btn btn-primary" to="/app/post">+ Create opportunity</Link>} />
      <div className="metric-grid">
        <Metric label="Provider verification" value={verified ? 'Verified' : pretty(o.organisation?.verification_status ?? 'pending')} tone={verified ? '#16a34a' : '#d97706'} note="From the registry check on your organisation" />
        <Metric label="Active opportunities" value={o.active_opportunities} note={`${o.closing_soon} closing within 14 days`} />
        <Metric label="Matched SMEs" value={o.matched_smes} note={`${o.high_fit} high-fit matches`} />
        <Metric label="Shortlisted" value={o.shortlisted} note={o.flagged ? `${o.flagged} flagged for review` : 'Nothing flagged'} />
      </div>
      {total > 0 && (
        <Panel title="Where your matches sit" sub="Across all your opportunities.">
          <div style={{ display: 'flex', height: 14, borderRadius: 8, overflow: 'hidden', background: '#eef2f7' }}>
            {QUADS.map((q) => o.by_quadrant[q] ? <div key={q} title={`${QUADRANT_LABEL[q]}: ${o.by_quadrant[q]}`} style={{ width: `${(o.by_quadrant[q]! / total) * 100}%`, background: QUADRANT_COLOR[q] }} /> : null)}
          </div>
          <div className="quad-legend">{QUADS.map((q) => <span key={q}><i style={{ background: QUADRANT_COLOR[q] }} />{QUADRANT_LABEL[q]} <b>{o.by_quadrant[q] ?? 0}</b></span>)}</div>
        </Panel>)}
      <Panel title="Your opportunities">
        {opps.data.length ? <div className="table-wrap"><table>
          <thead><tr><th>Opportunity</th><th>Type</th><th>Value</th><th>Closes</th><th>Award ready</th><th>Coachable</th><th>Other</th><th /></tr></thead>
          <tbody>{opps.data.map((x) => {
            const left = daysUntil(x.deadline)
            const qd = x.quadrants ?? {}
            return (
              <tr key={x.id}><td><b>{x.title}</b><br /><small>{pretty(x.sector)} · {x.province}</small></td>
                <td><Badge tone="purple">{KIND_LABEL[x.kind]}</Badge></td><td>{zar(x.contract_value)}</td>
                <td>{dateFmt(x.deadline)}{left !== null && left >= 0 && left <= 14 && <><br /><small style={{ color: '#b45309' }}>{left} days left</small></>}</td>
                <td className="mono"><b>{qd.award_now ?? 0}</b></td><td className="mono"><b>{qd.coachable ?? 0}</b></td>
                <td className="mono">{(qd.ready_weak_fit ?? 0) + (qd.develop ?? 0)}</td>
                <td><Link className="btn btn-outline btn-small" to={`/app/opportunities/${x.id}`}>Open</Link></td></tr>)
          })}</tbody></table></div> : <div className="empty"><strong>No opportunities yet</strong>Create your first one to start matching.</div>}
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ post */

interface ReqRow { type: string; value: string; mandatory: boolean; weight: number }
const VALUE_KEY: Record<string, string> = {
  sector: 'sector', province: 'province', min_years: 'years', min_turnover: 'amount', ownership: 'flag',
  capability: 'code', compliance_doc: 'doc', certification: 'doc',
}

export function PostOpportunity() {
  const { me } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const tax = useLoad(() => api.taxonomy())
  const role = (me?.role ?? 'corporate') as Role
  const kinds = KINDS_BY_ROLE[role] ?? ['procurement']
  const [kind, setKind] = useState<Kind>(kinds[0])
  const [f, setF] = useState({ title: '', description: '', deadline: '', sector: '', province: '', contract_value: 0, duration_months: 12, payment_terms_days: 30 })
  const [scope, setScope] = useState<{ code: string; value: number }[]>([{ code: '', value: 0 }])
  const [gap, setGap] = useState<string[]>([])
  const [reqs, setReqs] = useState<ReqRow[]>([])
  const [tender, setTender] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!tax.data) return <Spinner />
  const t = tax.data
  const options = (type: string): string[] | null =>
    type === 'sector' ? t.sectors : type === 'province' ? t.provinces : type === 'ownership' ? t.ownership
      : type === 'capability' ? t.capabilities.map((c) => c.code)
      : type === 'compliance_doc' || type === 'certification' ? t.credentials.map((c) => c.code) : null
  const setReq = (i: number, patch: Partial<ReqRow>) => setReqs(reqs.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  async function draft() {
    try {
      const { draft: d, source } = await api.extractOpportunity(tender)
      const rows: ReqRow[] = [
        ...(d.min_years != null ? [{ type: 'min_years', value: String(d.min_years), mandatory: true, weight: 5 }] : []),
        ...d.required_documents.map((x) => ({ type: 'compliance_doc', value: x, mandatory: true, weight: 10 })),
        ...d.capability_codes.map((x) => ({ type: 'capability', value: x, mandatory: true, weight: 10 })),
      ]
      setReqs([...reqs, ...rows]); setF({ ...f, sector: d.sector ?? f.sector, province: d.province ?? f.province })
      toast(source === 'llm' ? 'Draft rows added. Review and edit them below.' : 'Automatic reading is unavailable right now. Add rows by hand.', source === 'llm' ? 'success' : 'info')
    } catch (err) { setError((err as Error).message) }
  }

  async function submit(e: FormEvent) {
    e.preventDefault(); setError(null); setBusy(true)
    try {
      const requirements = reqs.map((r) => ({
        requirement_type: r.type, mandatory: r.mandatory, weight: r.weight,
        requirement_value: { [VALUE_KEY[r.type]]: r.type === 'min_years' || r.type === 'min_turnover' ? +r.value : r.value },
      }))
      const o = await api.createOpportunity({
        ...f, kind, description: f.description || null, deadline: f.deadline || null,
        scope_items: scope.filter((s) => s.code), transformation_gap: gap, requirements,
      })
      await api.runMatch(o.id)
      toast('Opportunity published and matched.')
      nav(`/app/opportunities/${o.id}`)
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  return (
    <>
      <Welcome title="Create an opportunity" text="Requirements are rules, not prose. Each row is a gate (mandatory) or a weighted preference, and that is what makes every match explainable." />
      <form onSubmit={submit}><Panel title="Opportunity details" right={<Badge tone="green">{FOCUS[role]}</Badge>}>
        <ErrorNote error={error} />
        <details style={{ marginBottom: 18 }}><summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>Draft requirements from tender text (optional)</summary>
          <div className="field" style={{ marginTop: 10 }}><textarea rows={4} value={tender} onChange={(e) => setTender(e.target.value)} />
            <span className="hint">An AI model proposes rows from the allowed list only. You review and edit them below.</span></div>
          <button type="button" className="btn btn-outline btn-small" disabled={tender.length < 20} onClick={draft}>Draft requirements</button></details>
        <div className="form-grid">
          {kinds.length > 1 && <div className="field"><label htmlFor="k">Type</label><select id="k" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>{kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}</select></div>}
          <div className="field full"><label htmlFor="t">Title</label><input id="t" required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
          <div className="field full"><label htmlFor="d">Description</label><textarea id="d" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
          <div className="field"><label htmlFor="s">Sector</label><select id="s" required value={f.sector} onChange={(e) => setF({ ...f, sector: e.target.value })}><option value="">Choose…</option>{t.sectors.map((s) => <option key={s} value={s}>{pretty(s)}</option>)}</select></div>
          <div className="field"><label htmlFor="p">Province</label><select id="p" required value={f.province} onChange={(e) => setF({ ...f, province: e.target.value })}><option value="">Choose…</option>{t.provinces.map((s) => <option key={s}>{s}</option>)}</select></div>
          <div className="field"><label htmlFor="v">{VALUE_LABEL[kind]}</label><input id="v" type="number" min={1} required value={f.contract_value || ''} onChange={(e) => setF({ ...f, contract_value: +e.target.value })} /></div>
          <div className="field"><label htmlFor="du">Duration (months)</label><input id="du" type="number" min={1} required value={f.duration_months} onChange={(e) => setF({ ...f, duration_months: +e.target.value })} /></div>
          <div className="field"><label htmlFor="dl">Closing date</label><input id="dl" type="date" value={f.deadline} onChange={(e) => setF({ ...f, deadline: e.target.value })} /></div>
          <div className="field"><label htmlFor="pt">Payment terms (days)</label><input id="pt" type="number" min={0} value={f.payment_terms_days} onChange={(e) => setF({ ...f, payment_terms_days: +e.target.value })} />
            <span className="hint">Drives the working-capital figure shown for each SME.</span></div>
        </div>
        <div className="form-section"><h4>Scope line items</h4>
          {scope.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
              <select aria-label="Capability" style={{ flex: 1 }} value={s.code} onChange={(e) => setScope(scope.map((x, j) => (j === i ? { ...x, code: e.target.value } : x)))}><option value="">Capability…</option>{t.capabilities.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}</select>
              <input aria-label="Value in rand" type="number" min={1} style={{ width: 160 }} placeholder="Value (R)" value={s.value || ''} onChange={(e) => setScope(scope.map((x, j) => (j === i ? { ...x, value: +e.target.value } : x)))} /></div>))}
          <button type="button" className="btn btn-outline btn-small" onClick={() => setScope([...scope, { code: '', value: 0 }])}>Add line</button></div>
        <div className="form-section"><h4>Transformation goal (optional)</h4>
          <div style={{ display: 'flex', gap: 18 }}>{t.ownership.map((o) => <label key={o} style={{ display: 'flex', gap: 8, fontSize: 13 }}><input type="checkbox" checked={gap.includes(o)} onChange={() => setGap(gap.includes(o) ? gap.filter((x) => x !== o) : [...gap, o])} />{pretty(o)}</label>)}</div></div>
        <div className="form-section"><h4>Requirement rows</h4>
          <p className="hint" style={{ marginBottom: 12 }}>Mandatory rows gate: a structural mismatch removes the SME, a missing document keeps them with a plan. The weight sets how many points an unmet preferred row costs.</p>
          {reqs.map((r, i) => (
            <div key={i} className="req-row">
              <div className="field" style={{ margin: 0 }}><label>Type</label><select value={r.type} onChange={(e) => setReq(i, { type: e.target.value, value: '' })}>{Object.keys(VALUE_KEY).map((k) => <option key={k} value={k}>{pretty(k)}</option>)}</select></div>
              <div className="field" style={{ margin: 0 }}><label>Value</label>{options(r.type) ? <select required value={r.value} onChange={(e) => setReq(i, { value: e.target.value })}><option value="">Choose…</option>{options(r.type)!.map((o) => <option key={o}>{o}</option>)}</select>
                : <input type="number" min={0} required value={r.value} onChange={(e) => setReq(i, { value: e.target.value })} />}</div>
              <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, paddingBottom: 10 }}><input type="checkbox" checked={r.mandatory} onChange={(e) => setReq(i, { mandatory: e.target.checked })} />Mandatory</label>
              <div className="field" style={{ margin: 0 }}><label>Weight: {r.weight}</label><input type="range" min={0} max={20} value={r.weight} onChange={(e) => setReq(i, { weight: +e.target.value })} /></div>
              <button type="button" className="btn btn-outline btn-small" onClick={() => setReqs(reqs.filter((_, j) => j !== i))}>Remove</button></div>))}
          <button type="button" className="btn btn-outline btn-small" onClick={() => setReqs([...reqs, { type: 'compliance_doc', value: '', mandatory: true, weight: 10 }])}>Add requirement</button></div>
        <div style={{ marginTop: 22 }}><button className="btn btn-primary" disabled={busy}>{busy ? 'Publishing…' : 'Publish and match'}</button></div>
      </Panel></form>
    </>
  )
}

/* ------------------------------------------------------------------ detail */

export function OpportunityDetail() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const o = useLoad(() => api.opportunity(id), [id])
  const rows = useLoad(() => api.matches(id), [id])
  const cons = useLoad(() => api.consortium(id), [id])
  const [busy, setBusy] = useState(false)
  const [qf, setQf] = useState<Quadrant | 'all'>('all')
  if (o.error) return <ErrorNote error={o.error} />
  if (!o.data || !rows.data) return <Spinner />
  const opp = o.data
  const all = rows.data
  const procurement = opp.kind === 'procurement'
  async function rematch() {
    setBusy(true)
    try { rows.setData(await api.runMatch(id)); cons.reload(); toast('Matching re-run.') } catch (err) { toast((err as Error).message, 'error') } finally { setBusy(false) }
  }
  async function decide(mid: string, a: 'shortlist' | 'reject') {
    try { await api.decide(mid, a); rows.setData(await api.matches(id)); toast(a === 'shortlist' ? 'Shortlisted.' : 'Rejected.') } catch (err) { toast((err as Error).message, 'error') }
  }
  const c = cons.data?.consortium
  return (
    <>
      <Welcome eyebrow={KIND_LABEL[opp.kind]} title={opp.title}
        text={`${zar(opp.contract_value)} · ${pretty(opp.sector)} · ${opp.province} · ${opp.duration_months} months · closes ${dateFmt(opp.deadline)}`}
        action={<button className="btn btn-outline" disabled={busy} onClick={rematch}>{busy ? 'Matching…' : 'Re-run matching'}</button>} />
      {opp.description && <p style={{ maxWidth: 800, fontSize: 14, lineHeight: 1.7, color: '#475467', marginTop: -6 }}>{opp.description}</p>}
      <Explainer />
      <div className="grid-2" style={{ gridTemplateColumns: '1.4fr 1fr' }}>
        <Panel title="Fit and readiness" sub="One dot per SME. Click a dot for the full breakdown. The dashed lines mark 60.">
          <QuadrantChart dots={rows.data.map((r) => ({ key: r.match_id, fit: r.fit, readiness: r.readiness, quadrant: r.quadrant, overtrading: r.risk_flags.overtrading && procurement, label: r.sme_name }))}
            onSelect={(k) => nav(`/app/matches/${k}`)} />
          <QuadrantLegend />
        </Panel>
        <div>
          {c && <Panel title="Consortium proposal" right={<Badge tone="purple">{c.coverage_pct}% covered</Badge>}>
            <p style={{ fontSize: 13, color: '#475467', lineHeight: 1.6, marginTop: 0 }}>No single SME covers this scope. These {c.members.length} together do.</p>
            {c.members.map((m) => <div key={m.sme_id} className="verify-row"><span className="check-circle">{m.sme_id === c.lead.sme_id ? '★' : '·'}</span><div><b>{m.name}</b><small>{m.sme_id === c.lead.sme_id ? 'Proposed lead (most ready)' : 'Member'}</small></div><span /></div>)}
            {c.uncovered_codes.length > 0 && <p className="hint">Still uncovered: {c.uncovered_codes.join(', ')}</p>}</Panel>}
          <Panel title="Requirements driving the score" sub="Rules, not prose.">
            {opp.requirements.length ? opp.requirements.map((r) => (
              <div key={r.id} className="verify-row"><span className={`check-circle ${r.mandatory ? '' : 'idle'}`}>{r.mandatory ? '!' : '+'}</span>
                <div><b>{pretty(r.requirement_type)}: {String(Object.values(r.requirement_value)[0])}</b><small>{r.mandatory ? 'Mandatory gate' : `Preferred, weight ${r.weight}`}</small></div><span /></div>)) : <p className="hint">No requirement rows. Scoring uses capability, capacity, geography and experience only.</p>}
          </Panel>
        </div>
      </div>
      <Panel title="Ranked shortlist" sub="Sorted by a blended score for convenience only. Decide on the two axes.">
        <div className="chips" style={{ marginTop: 0, marginBottom: 14 }}>
          {(['all', ...QUADS] as (Quadrant | 'all')[]).map((k) => {
            const n = k === 'all' ? all.length : all.filter((r) => r.quadrant === k).length
            return <button key={k} className="chip" style={qf === k ? { background: '#4c1d95', color: '#fff', borderColor: '#4c1d95' } : undefined} onClick={() => setQf(k)}>{k === 'all' ? 'All' : QUADRANT_LABEL[k]} · {n}</button>
          })}
        </div>
        {rows.data.length ? <div className="table-wrap"><table>
          <thead><tr><th>SME</th><th>Fit</th><th>Readiness</th><th>Position</th>{procurement && <th>Risk</th>}<th>Verification</th><th /></tr></thead>
          <tbody>{rows.data.filter((r) => qf === 'all' || r.quadrant === qf).map((r) => (
            <tr key={r.match_id}><td><Link to={`/app/matches/${r.match_id}`} style={{ color: 'var(--purple)', fontWeight: 700 }}>{r.sme_name}</Link></td>
              <td className="mono">{r.fit}<MiniBar value={r.fit} /></td><td className="mono">{r.readiness}<MiniBar value={r.readiness} /></td>
              <td><QuadrantBadge q={r.quadrant} />{r.gap_count > 0 && <><br /><small>{r.gap_count} gap{r.gap_count > 1 ? 's' : ''}</small></>}</td>
              {procurement && <td>{[r.risk_flags.overtrading && 'Overtrading', r.risk_flags.concentration && 'Concentration'].filter(Boolean).map((x) => <Badge key={String(x)} tone="red">{x}</Badge>)}</td>}
              <td><Badge tone={r.verification_status === 'verified' ? 'green' : 'amber'}>{r.verification_status === 'verified' ? 'Verified' : 'In review'}</Badge></td>
              <td><div className="table-actions">{r.status === 'matched'
                ? <><button className="btn btn-primary btn-small" onClick={() => decide(r.match_id, 'shortlist')}>Shortlist</button><button className="btn btn-outline btn-small" onClick={() => decide(r.match_id, 'reject')}>Reject</button></>
                : <Badge tone={r.status === 'shortlisted' ? 'green' : 'gray'}>{pretty(r.status)}</Badge>}</div></td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>No matches yet</strong>Run matching, or relax a mandatory requirement.</div>}
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ shortlist and directory */

export function ShortlistPage() {
  const list = useLoad(() => api.shortlist())
  if (!list.data) return <Spinner />
  return (
    <>
      <Welcome title="Shortlists" text="SMEs you have shortlisted across your opportunities. Every shortlist action is in the audit log." />
      <Panel>
        {list.data.length ? <div className="table-wrap"><table>
          <thead><tr><th>SME</th><th>Opportunity</th><th>Fit</th><th>Readiness</th><th>Position</th><th>Application</th><th /></tr></thead>
          <tbody>{list.data.map((r) => (
            <tr key={r.match_id}><td><b>{r.sme}</b></td><td>{r.opportunity}</td><td className="mono">{r.fit}</td><td className="mono">{r.readiness}</td>
              <td><QuadrantBadge q={r.quadrant} />{r.gap_count > 0 && <><br /><small>{r.gap_count} gap{r.gap_count > 1 ? 's' : ''} to close</small></>}</td>
              <td>{r.application ? <Badge tone="blue">{pretty(r.application)}</Badge> : <span className="hint">Not applied</span>}</td>
              <td><Link className="btn btn-outline btn-small" to={`/app/matches/${r.match_id}`}>Review</Link></td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>Nothing shortlisted yet</strong>Open an opportunity and shortlist SMEs from the ranked list.</div>}
      </Panel>
    </>
  )
}

export function SmeDirectory() {
  const dir = useLoad(() => api.directory())
  const tax = useLoad(() => api.taxonomy())
  const [q, setQ] = useState('')
  const [sector, setSector] = useState('')
  if (!dir.data || !tax.data) return <Spinner />
  const label = Object.fromEntries(tax.data.capabilities.map((c) => [c.code, c.label]))
  const rows = dir.data.filter((s) => (!sector || s.sector === sector) && s.name.toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <Welcome title="Verified SME directory" text="Businesses that chose to be visible. Verification reflects the checks actually run; ownership details are deliberately not listed here." />
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <input aria-label="Search by name" placeholder="Search by name" value={q} onChange={(e) => setQ(e.target.value)} style={{ border: '1px solid #d7deea', borderRadius: 11, padding: '10px 13px', minWidth: 260 }} />
        <select aria-label="Sector" value={sector} onChange={(e) => setSector(e.target.value)} style={{ border: '1px solid #d7deea', borderRadius: 11, padding: '10px 13px' }}>
          <option value="">All sectors</option>{tax.data.sectors.map((s) => <option key={s} value={s}>{pretty(s)}</option>)}</select>
        <span className="hint" style={{ alignSelf: 'center' }}>{rows.length} of {dir.data.length}</span>
      </div>
      <div className="grid-3">{rows.map((s) => (
        <div className="panel" key={s.id} style={{ marginBottom: 0 }}>
          <div className="panel-head"><div><h3>{s.name}</h3><p>{pretty(s.sector)} · {s.province} · {s.years_trading} yrs</p></div>
            <Badge tone={s.verification_status === 'verified' ? 'green' : 'amber'}>{s.verification_status === 'verified' ? 'Verified' : 'In review'}</Badge></div>
          <p className="hint" style={{ margin: 0 }}>{s.capability_codes.map((c) => label[c] ?? c).join(', ')}</p>
          <p className="hint" style={{ marginTop: 10 }}>{s.checks_passed} registry/tax checks passed · {s.documents_on_file} documents on file</p>
        </div>))}</div>
    </>
  )
}
