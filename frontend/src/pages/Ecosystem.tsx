import { api, pretty, zar } from '../api'
import { useLoad } from '../hooks'
import { Badge, Metric, Panel, Spinner, Welcome } from '../ui'

const n = (v: number | string) => (typeof v === 'number' ? v : 0)

function Bar({ value, max, tone = 'var(--purple)' }: { value: number; max: number; tone?: string }) {
  return <div className="progress" style={{ height: 8 }} aria-hidden><i style={{ width: `${Math.min(100, (value / Math.max(1, max)) * 100)}%`, background: tone }} /></div>
}

/** The programme view for YES: where demand is, where supply is thin, and what has been delivered.
 *  Aggregates only. Counts under three are suppressed so no single business can be picked out. */
export function Ecosystem() {
  const d = useLoad(() => api.ecosystem())
  if (d.error) return <p className="callout red">{d.error}</p>
  if (!d.data) return <Spinner />
  const e = d.data
  const t = e.totals
  const maxFunnel = Math.max(1, ...e.funnel.map((f) => f.count))
  const maxPressure = Math.max(1, ...e.sectors.map((s) => s.pressure))
  const maxSkill = Math.max(1, ...e.skills.map((s) => Math.max(s.requested, s.businesses)))
  return (
    <>
      <Welcome hero eyebrow="Ecosystem" title="Where small businesses meet opportunity"
        text="Demand, supply and outcomes across every corporate and funder. Aggregates only: no business is named, and small counts are hidden." />
      <div className="metric-grid">
        <Metric label="Businesses on the platform" value={t.businesses} note={`${t.youth_owned} youth-owned`} />
        <Metric label="Open opportunity value" value={zar(t.open_value)} tone="#7c3aed" note={`${t.opportunities} opportunities`} />
        <Metric label="Value awarded" value={zar(t.awarded_value)} note={`${t.awards} award${t.awards === 1 ? '' : 's'}`} />
        <Metric label="Jobs potential" value={e.employment.jobs_potential} note="indicative, see assumption" />
      </div>
      <div className="grid-2">
        <Panel title="From match to award" sub="How far matches travel. The drop between stages shows where help is needed.">
          {e.funnel.map((f) => (
            <div key={f.stage} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>{f.stage}</span><b className="mono">{f.count}</b></div>
              <Bar value={f.count} max={maxFunnel} />
            </div>))}
          <p className="hint" style={{ marginBottom: 0 }}>Match quality: {Object.entries(e.quadrants).map(([q, c]) => `${pretty(q)} ${c}`).join(' · ') || 'no matches yet'}</p>
        </Panel>
        <Panel title="Most common credential gaps" sub="Mandatory documents blocking good-fit matches right now.">
          {e.credential_gaps.length ? e.credential_gaps.map((g) => (
            <div key={g.label} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>{g.label}</span><b className="mono">{g.matches_blocked} matches</b></div>
              <Bar value={g.matches_blocked} max={e.credential_gaps[0].matches_blocked} tone="#f59e0b" />
            </div>)) : <p className="hint" style={{ margin: 0 }}>No gaps on record.</p>}
          <p className="hint" style={{ marginBottom: 0 }}>This is where a targeted programme (for example, a tax-clearance clinic) frees the most contract value. The Unlock Map prices it.</p>
        </Panel>
      </div>
      <Panel title="Inclusion" sub="Language never enters a score. These figures show whether working in your own language costs a business anything."
        right={<Badge tone="purple">{e.inclusion.home_language_pct}% work in a home language</Badge>}>
        <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <Metric label="Home-language businesses" value={`${e.inclusion.home_language_pct}%`} note={`of ${e.inclusion.businesses} on the platform`} />
          <Metric label="Used voice" value={e.inclusion.voice_users} note="read aloud or spoken search" />
          <Metric label="Signed up with help" value={e.inclusion.assisted} note="by a support programme" />
        </div>
        <div className="table-wrap"><table>
          <thead><tr><th>Language</th><th>Businesses</th><th>Profile complete</th><th>Applied</th><th>Awarded</th></tr></thead>
          <tbody>{e.inclusion.languages.map((l) => (
            <tr key={l.language}><td><b>{l.label}</b>{!l.reviewed && <> <Badge tone="amber">Beta</Badge></>}</td><td>{l.businesses}</td>
              <td>{l.profile_complete_pct === null ? '–' : `${l.profile_complete_pct}%`}</td><td>{l.applied}</td><td>{l.awarded}</td></tr>))}</tbody>
        </table></div>
        <p className="hint" style={{ marginBottom: 0 }}>{e.inclusion.note} Figures come from this demo database.</p>
      </Panel>
      <Panel title="Sector demand against supply" sub="Pressure is open opportunities per business. A high number means corporates want more than the platform can supply.">
        <div className="table-wrap"><table>
          <thead><tr><th>Sector</th><th>Businesses</th><th>Opportunities</th><th>Open value</th><th style={{ minWidth: 160 }}>Pressure</th></tr></thead>
          <tbody>{e.sectors.map((s) => (
            <tr key={s.sector}><td><b>{pretty(s.sector)}</b></td><td>{s.businesses}</td><td>{s.opportunities}</td><td>{zar(s.value)}</td>
              <td><span className="mono">{s.pressure}</span><Bar value={s.pressure} max={maxPressure} tone={s.pressure >= 1 ? '#dc2626' : 'var(--purple)'} /></td></tr>))}</tbody>
        </table></div>
      </Panel>
      <div className="grid-2">
        <Panel title="Skills corporates ask for" sub="Requested in opportunities, against businesses that hold the capability.">
          {e.skills.map((s) => (
            <div key={s.code} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, gap: 8 }}>
                <span>{s.label} {s.shortfall && <Badge tone="red">Shortfall</Badge>}</span>
                <span className="mono hint">{s.requested} asked · {s.businesses} offer</span></div>
              <Bar value={s.requested} max={maxSkill} tone="#2563eb" />
              <Bar value={s.businesses} max={maxSkill} tone="#7c3aed" />
            </div>))}
          <p className="hint" style={{ marginBottom: 0 }}><span style={{ color: '#2563eb' }}>Blue</span> is demand, <span style={{ color: '#7c3aed' }}>purple</span> is supply.</p>
        </Panel>
        <div>
          <Panel title="Underserved categories" sub="Requested by corporates, with two or fewer businesses able to deliver.">
            {e.underserved.length ? e.underserved.map((u) => (
              <div key={u.label} className="metric-row"><span>{u.label}</span><Badge tone="amber">{u.requested} asked · {u.businesses} offer</Badge></div>
            )) : <p className="hint" style={{ margin: 0 }}>No category is under-supplied right now.</p>}
          </Panel>
          <Panel title="Where businesses and opportunities are" sub="By province.">
            <div className="table-wrap"><table>
              <thead><tr><th>Province</th><th>Businesses</th><th>Opportunities</th></tr></thead>
              <tbody>{e.provinces.map((p) => (
                <tr key={p.province}><td>{p.province}</td><td>{p.businesses}</td>
                  <td>{p.opportunities}{n(p.opportunities) > 0 && n(p.businesses) === 0 && <> <Badge tone="red">No supply</Badge></>}</td></tr>))}</tbody>
            </table></div>
          </Panel>
        </div>
      </div>
      <div className="grid-2">
        <Panel title="How corporates rate delivery" sub={`${e.quality.reviews} review${e.quality.reviews === 1 ? '' : 's'} across all businesses`}>
          {e.quality.reviews ? e.quality.criteria.map((c) => (
            <div key={c.key} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>{c.label}</span><b className="mono">{c.average ?? '–'}</b></div>
              <Bar value={c.average ?? 0} max={5} />
            </div>)) : <p className="hint" style={{ margin: 0 }}>Ratings appear after corporates review awarded work.</p>}
          <p className="hint" style={{ marginBottom: 0 }}>A low average on one criterion shows where support would help most, such as delivery or compliance.</p>
        </Panel>
        <Panel title="Employment potential" sub="An indicative estimate, not a measured result.">
          <div className="perf-head"><b className="perf-score">{e.employment.jobs_potential}</b><span className="hint">jobs potential</span></div>
          <p className="callout gray" style={{ marginBottom: 0, fontSize: 13 }}>{e.employment.assumption}</p>
        </Panel>
      </div>
    </>
  )
}
