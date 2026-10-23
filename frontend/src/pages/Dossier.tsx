import { useNavigate, useParams } from 'react-router-dom'
import { api, dateFmt, pretty, QUADRANT_LABEL, zar } from '../api'
import { useLoad } from '../hooks'
import { Badge, ErrorNote, Spinner, VerificationRow } from '../ui'

/** One printable record of a decision: the rules, the scores, the sources and the history. */
export function Dossier() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const q = useLoad(() => api.dossier(id), [id])
  if (q.error) return <ErrorNote error={q.error} />
  if (!q.data) return <Spinner />
  const d = q.data
  const stamp = new Date(d.generated_at).toLocaleString('en-ZA')
  return (
    <article className="dossier">
      <div className="no-print" style={{ display: 'flex', gap: 10, marginBottom: 18 }}>
        <button className="btn btn-outline" onClick={() => nav(-1)}>Back</button>
        <button className="btn btn-primary" onClick={() => window.print()}>Print or save as PDF</button>
      </div>
      <header style={{ borderBottom: '2px solid var(--ink)', paddingBottom: 12, marginBottom: 18 }}>
        <small className="hint">Decision dossier · model {d.model_version} · generated {stamp}</small>
        <h1 style={{ font: '800 26px Manrope', margin: '6px 0' }}>{d.sme.name} for {d.opportunity.title}</h1>
        <p className="hint" style={{ margin: 0 }}>{d.opportunity.provider} · {pretty(d.opportunity.kind)} · {zar(d.opportunity.contract_value)} · {d.opportunity.duration_months} months · closes {dateFmt(d.opportunity.deadline)}</p>
      </header>

      <h2>Outcome</h2>
      <p>Position <b>{QUADRANT_LABEL[d.result.quadrant]}</b>. Fit <b>{d.result.fit}</b>, readiness <b>{d.result.readiness}</b> (award-ready needs 60 on both). Current status <b>{pretty(d.status)}</b>. A person made the decision; the scores informed it.</p>
      {d.matches_decision_snapshot !== null && (
        <p className="callout gray" style={{ marginTop: 0 }}>{d.matches_decision_snapshot
          ? 'The live scores equal the scores frozen when the decision was made.'
          : 'The live scores have changed since the decision. The frozen copy in the history below is the record of what the decision-maker saw.'}</p>)}

      <h2>Rules applied</h2>
      <p className="hint">Requirements the provider set. Mandatory rows gate; preferred rows cost points when unmet.</p>
      <table><thead><tr><th>Rule</th><th>Value</th><th>Kind</th></tr></thead><tbody>
        {d.rules.map((r, i) => <tr key={i}><td>{pretty(r.type)}</td><td>{String(Object.values(r.value)[0])}</td><td>{r.mandatory ? 'Mandatory gate' : `Preferred, weight ${r.weight}`}</td></tr>)}
        {d.rules.length === 0 && <tr><td colSpan={3}>No requirement rows. Scored on capability, capacity, geography and experience only.</td></tr>}
      </tbody></table>

      <h2>How fit was scored</h2>
      <table><tbody>{Object.entries(d.result.components ?? {}).map(([k, v]) => <tr key={k}><td>{k === 'preferred_requirements' ? 'Unmet preferred rows' : pretty(k)}</td><td className="mono" style={{ textAlign: 'right' }}>{Number(v).toFixed(1)}</td></tr>)}</tbody></table>

      <h2>Readiness gaps</h2>
      {d.result.gaps?.length ? <table><thead><tr><th>Credential</th><th>Issuer</th><th>Days</th><th>Cost</th><th>Mandatory</th></tr></thead><tbody>
        {d.result.gaps.map((g) => <tr key={g.credential}><td>{g.label} ({pretty(g.status)})</td><td>{g.issuer}</td><td>{g.days}</td><td>{zar(g.cost_zar)}</td><td>{g.mandatory ? 'Yes' : 'No'}</td></tr>)}
      </tbody></table> : <p>No open gaps.</p>}

      <h2>Capacity risk</h2>
      <p>Overtrading: <b>{d.result.risk_flags.overtrading ? `flagged (${d.result.risk_flags.overtrading_pct}% of turnover)` : 'clear'}</b>. Concentration: <b>{d.result.risk_flags.concentration ? `flagged (${d.result.risk_flags.concentration_pct}%)` : 'clear'}</b>. Working capital before first payment: <b>{zar(d.result.risk_flags.working_capital_zar)}</b>. Flags never reduce the fit score.</p>

      <h2>Verification sources</h2>
      {d.verifications.length ? d.verifications.map((v) => <VerificationRow key={v.id} v={v} />) : <p>No checks on record.</p>}

      <h2>Decision history</h2>
      <p className="hint">From the audit log, which the application cannot edit or delete.</p>
      {d.decisions.length ? <table><thead><tr><th>When</th><th>Action</th><th>By</th><th>Scores at the time</th></tr></thead><tbody>
        {d.decisions.map((x, i) => <tr key={i}><td>{new Date(x.at).toLocaleString('en-ZA')}</td><td>{pretty(x.action)}</td><td>{x.by_role ? `${pretty(x.by_role)}${x.by_organisation ? `, ${x.by_organisation}` : ''}` : 'System'}</td>
          <td>{x.snapshot ? `Fit ${x.snapshot.fit}, readiness ${x.snapshot.readiness}, ${QUADRANT_LABEL[x.snapshot.quadrant]}` : <Badge tone="gray">no snapshot</Badge>}</td></tr>)}
      </tbody></table> : <p>No decision has been recorded yet.</p>}
      <p className="hint" style={{ marginTop: 24 }}>Scores are produced by fixed, versioned rules. An AI model may word summaries but never sets a score. Verification sources marked mock are simulated in this pilot.</p>
    </article>
  )
}
