import { api, dateFmt, pretty } from '../api'
import { useLoad } from '../hooks'
import { Badge, Metric, Panel, Spinner, Welcome, useToast } from '../ui'
import { DisputeQueue } from './Feedback'

export function AdminQueue() {
  const toast = useToast()
  const q = useLoad(() => api.queue())
  if (!q.data) return <Spinner />
  async function act(kind: 'v' | 'm', id: string, decision: 'approved' | 'rejected') {
    try {
      await (kind === 'v' ? api.reviewVerification(id, decision) : api.reviewMatch(id, decision))
      toast(`Marked ${decision}. Recorded in the audit log with your reviewer id.`); q.reload()
    } catch (err) { toast((err as Error).message, 'error') }
  }
  const buttons = (kind: 'v' | 'm', id: string) => (
    <div className="table-actions">
      <button className="btn btn-primary btn-small" onClick={() => act(kind, id, 'approved')}>Approve</button>
      <button className="btn btn-outline btn-small" onClick={() => act(kind, id, 'rejected')}>Reject</button></div>)
  return (
    <>
      <Welcome eyebrow="Human in the loop" title="Review queue" text="The system ranks. A person decides. Every decision is written to the audit log with your reviewer id, and a rejected document is treated as missing." />
      <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', maxWidth: 520 }}>
        <Metric label="Flagged verifications" value={q.data.verifications.length} /><Metric label="Flagged matches" value={q.data.matches.length} />
      </div>
      <Panel title="Flagged verifications" sub="Checks that did not pass. Nobody is silently rejected.">
        {q.data.verifications.length ? <div className="table-wrap"><table>
          <thead><tr><th>Organisation</th><th>Check</th><th>Result</th><th>Source</th><th>Checked</th><th /></tr></thead>
          <tbody>{q.data.verifications.map((v) => (
            <tr key={v.id}><td><b>{v.organisation ?? 'Unknown organisation'}</b></td><td>{v.subject_type === 'document' && v.document_type ? `Document · ${v.document_type}` : pretty(v.subject_type)}</td>
              <td><Badge tone="amber">{pretty(v.result)}</Badge></td><td><small>{v.source_label}</small></td><td>{dateFmt(v.checked_at)}</td><td>{buttons('v', v.id)}</td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>Nothing waiting</strong>Flagged checks appear here.</div>}
      </Panel>
      <Panel title="Flagged matches" sub="Matches involving an SME with an unresolved verification flag.">
        {q.data.matches.length ? <div className="table-wrap"><table>
          <thead><tr><th>SME</th><th>Opportunity</th><th>Fit</th><th>Readiness</th><th>Reason</th><th /></tr></thead>
          <tbody>{q.data.matches.map((x) => (
            <tr key={x.id}><td><b>{x.sme}</b></td><td>{x.opportunity}</td><td className="mono">{x.fit}</td><td className="mono">{x.readiness}</td><td><small>{x.reason}</small></td><td>{buttons('m', x.id)}</td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>Nothing waiting</strong></div>}
      </Panel>
      <DisputeQueue />
    </>
  )
}
