import { api, pretty, zar } from '../api'
import { useLoad } from '../hooks'
import { Badge, Metric, Panel, Spinner, Welcome } from '../ui'

/** The Unlock Map: which credential holds back the most good-fit SMEs, and the value behind it. */
export function UnlockMap() {
  const d = useLoad(() => api.bottlenecks())
  if (d.error) return <p className="callout red">{d.error}</p>
  if (!d.data) return <Spinner />
  const { rows, total_value_locked, smes_considered, opportunities_considered } = d.data
  const max = Math.max(1, ...rows.map((r) => r.value_locked))
  const top = rows[0]
  return (
    <>
      <Welcome eyebrow="Ecosystem insight" title="Unlock Map"
        text="The documents holding back SMEs who already fit. Fix one credential and every opportunity behind it opens up. Aggregates only: no business is named." />
      <div className="metric-grid">
        <Metric label="Contract value held back" value={zar(total_value_locked)} note="Behind a missing or expired credential" tone="#7c3aed" />
        <Metric label="Top bottleneck" value={top ? top.credential : '–'} note={top ? top.label : 'Nothing is blocked'} />
        <Metric label="SMEs considered" value={smes_considered} note="Visible to providers" />
        <Metric label="Open opportunities" value={opportunities_considered} note="Across all providers" />
      </div>
      <Panel title="Credentials ranked by contract value they hold back" sub="A business counts when it fits (60 or more) and is missing or has an expired mandatory credential.">
        {rows.length ? rows.map((r) => (
          <div key={r.credential} style={{ padding: '14px 0', borderBottom: '1px solid #eef1f5' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
              <div><b>{r.label}</b> <small className="hint">{r.issuer} · {r.days} days · {r.cost_zar ? zar(r.cost_zar) : 'no cost'}</small></div>
              <b style={{ fontFamily: 'Manrope' }}>{zar(r.value_locked)}</b>
            </div>
            <div className="progress" style={{ height: 10, margin: '8px 0' }} aria-hidden><i style={{ width: `${(r.value_locked / max) * 100}%` }} /></div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Badge tone="amber">{r.smes_blocked} SMEs blocked</Badge>
              <Badge tone="purple">{r.opportunities_blocked} {r.opportunities_blocked === 1 ? 'opportunity' : 'opportunities'}</Badge>
              <Badge tone="green">{r.would_unlock} become award-ready if this is the only gap</Badge>
            </div>
          </div>)) : <div className="empty"><strong>Nothing is blocked</strong>Every good-fit SME is ready.</div>}
      </Panel>
      <div className="callout blue">What a funder or development body can do with this: fund a one-off clinic for the top credential. {top ? `${pretty(top.credential)} alone holds back ${zar(top.value_locked)} of contracts today.` : ''}</div>
    </>
  )
}
