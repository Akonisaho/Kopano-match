import { api, pretty, zar } from '../api'
import { useLoad } from '../hooks'
import { Badge, Metric, Panel, Spinner, Welcome, useToast } from '../ui'

function Bars({ rows }: { rows: { name: string; value: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  return (
    <>
      {rows.map((r) => (
        <div key={r.name} style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>{pretty(r.name)}</span><b className="mono">{zar(r.value)}</b></div>
          <div className="progress" style={{ height: 8 }} aria-hidden><i style={{ width: `${(r.value / max) * 100}%` }} /></div>
        </div>
      ))}
    </>
  )
}

/** What reached SMEs: the number a buyer reports on and a funder asks for. Aggregates only. */
export function ImpactPage() {
  const toast = useToast()
  const d = useLoad(() => api.impact())
  if (d.error) return <p className="callout red">{d.error}</p>
  if (!d.data) return <Spinner />
  const x = d.data

  async function exportCsv() {
    try {
      const url = URL.createObjectURL(await api.impactCsv())
      const a = document.createElement('a'); a.href = url; a.download = 'kopano-impact.csv'; a.click(); URL.revokeObjectURL(url)
    } catch (err) { toast((err as Error).message, 'error') }
  }

  if (x.awards === 0) {
    return (
      <>
        <Welcome eyebrow="Impact" title="Impact report" text="Awards appear here once you record them. No business is named in this report." />
        <Panel><div className="empty"><strong>No awards recorded yet</strong>Shortlist an SME on an opportunity, then press Award. The report fills in from there.</div></Panel>
      </>
    )
  }
  const gap = x.awarded_despite_gap
  return (
    <>
      <Welcome eyebrow="Impact" title="Impact report"
        text="What your opportunities actually delivered to small businesses. Aggregates only: no business is named."
        action={<button className="btn btn-outline" onClick={exportCsv}>Export CSV</button>} />
      <div className="metric-grid">
        <Metric label="Value awarded" value={zar(x.value_awarded)} tone="#7c3aed" note={`${x.awards} award${x.awards === 1 ? '' : 's'}`} />
        <Metric label="SMEs awarded" value={x.smes_awarded} note={`${x.applications} applications`} />
        <Metric label="Application to award" value={`${x.conversion_pct}%`} note="of applications awarded" />
        <Metric label="Days to award" value={x.days_to_award_median ?? '–'} note="median, from publication" />
      </div>
      <div className="callout purple" style={{ marginTop: 0, marginBottom: 18, background: '#faf5ff', color: '#4c1d95', fontSize: 14 }}>
        <b>{gap.awards} award{gap.awards === 1 ? '' : 's'} worth {zar(gap.value)}</b> went to businesses that still had a document gap when they were awarded.
        {' '}A strict "must hold every document" filter would have rejected them. <Badge tone="purple">Coached, not discarded</Badge>
      </div>
      <div className="grid-2">
        <Panel title="Who it reached" sub="Share of the value awarded that went to businesses with this ownership.">
          {(['youth', 'black', 'black_women'] as const).map((f) => (
            <div key={f} style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>{pretty(f)}-owned</span><b className="mono">{x.ownership[f].share_pct}% <span className="hint">({x.ownership[f].awards} awards)</span></b></div>
              <div className="progress" style={{ height: 8 }} aria-hidden><i style={{ width: `${x.ownership[f].share_pct}%` }} /></div>
            </div>))}
          <p className="hint">Ownership is shown only in aggregate, for the buyer that made the award.</p>
        </Panel>
        <Panel title="Where the value went"><h4 style={{ fontSize: 12, margin: '0 0 8px' }}>By province</h4><Bars rows={x.by_province} />
          <h4 style={{ fontSize: 12, margin: '16px 0 8px' }}>By sector</h4><Bars rows={x.by_sector} /></Panel>
      </div>
    </>
  )
}
